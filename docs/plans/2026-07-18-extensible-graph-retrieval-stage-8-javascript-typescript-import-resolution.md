# Plan: Extensible Graph Retrieval Stage 8 — Deterministic JavaScript/TypeScript Import Resolution

- **Status:** approved for implementation by owner on 2026-07-18
- **Date:** 2026-07-18
- **Repository:** `/Users/brummerv/loci`
- **Governing design:** `docs/design/2026-07-13-extensible-graph-retrieval-design.md`
- **Predecessor:** `docs/plans/2026-07-15-extensible-graph-retrieval-stage-7-go-import-resolution.md`
- **Live baseline:** commit `6f4f3d63c8c143787b242dadc41bc8d6550ba46d`
- **Collected baseline:** 590 tests
- **Frozen benchmark:** `/Users/brummerv/llm-wiki/tests/fixtures/graph_shape_traversal_stage3.json`
- **Frozen benchmark SHA-256:** `c52def1bdf592ad735149d199910f74183598eccd9ccf8064335fa0cd0e84e27`

## Goal

Complete Loci's JavaScript and TypeScript dependency resolution for a bounded,
static, repository-contained contract.

Today Loci can extract static ECMAScript imports and re-exports, but it resolves
only relative specifiers against `.ts`, `.tsx`, and `.js` files. Every package
name is reported as external. Stage 8 will let Loci use explicit repository
evidence from:

- the full JavaScript/TypeScript source-extension family;
- `tsconfig.json` and `jsconfig.json` resolution options;
- contained `package.json` package entry points, private import maps, and
  self-references;
- declared package-json workspaces and `pnpm-workspace.yaml`; and
- source-package dependency declarations.

The result remains one directed, evidence-backed edge from the importing file
to one exact indexed file. If repository evidence cannot identify exactly one
file, the observation remains inspectable and unresolved.

"Complete" in this plan means complete for the explicitly supported static
contract below. It does not mean reproducing every runtime loader, bundler,
package-manager install, generated output tree, or TypeScript release by
executing those tools.

## Plain-language Outcome

Given a monorepo like:

~~~text
repo/
├── package.json                     workspaces: ["apps/*", "packages/*"]
├── apps/web/
│   ├── package.json                 depends on @repo/core
│   └── src/page.ts                  imports @repo/core/format
└── packages/core/
    ├── package.json                 exports ./format -> ./src/format.ts
    └── src/format.ts
~~~

Loci will be able to persist:

~~~text
apps/web/src/page.ts::__file__#file
    -- loci:imports / import-resolved -->
packages/core/src/format.ts::__file__#file
~~~

It will be able to explain that the target came from workspace membership plus
the target package's `exports` map. If the export instead points only to
`./dist/format.js` and that file is not indexed, Loci will report
`unresolved/not_indexed`; it will not guess that `src/format.ts` is probably the
source.

This is the core trust boundary: useful monorepo navigation without turning the
graph into a machine-dependent simulation of an install.

## Authorization and Review Posture

The owner approved the corrected dependency-layer order and the use of
workload-routed language guidance, with the explicit caveat that Anvil's
guidance must evolve as project evidence and ecosystems change.

The owner approved this implementation boundary on 2026-07-18, authorizing
resolver implementation under the following constraints:

1. exact file targets rather than new JavaScript package nodes;
2. contained controls only, with no installed `node_modules` inspection;
3. automatic standard config discovery rather than guessing which custom
   `tsconfig.*.json` a build command might select;
4. static `import`/source-bearing `export` observations only; and
5. honest unresolved results when build output or loader-specific evidence is
   missing.

The project rule that substantial approved work is committed and pushed
automatically applies to the resulting implementation slices.

## Reconciliation with the Governing Documents

### Extensible graph design

`docs/design/2026-07-13-extensible-graph-retrieval-design.md` now places this
stage first after Stage 7. It requires a separately reviewed, deterministic
JavaScript/TypeScript completion step covering package, workspace, and compiler
configuration semantics. It also defines completion as a bounded static
contract without execution or network access.

This plan implements that corrected order and leaves Cargo-aware Rust next.

### Earlier graph trust design

`docs/design/2026-06-10-graph-layer-design.md` requires:

- no unresolved relationship presented as fact;
- directed `A imports B` edges from importer to dependency;
- deterministic evidence before heuristic inference; and
- no bare-name repository fallback.

Stage 8 therefore resolves a package name only through explicit workspace,
manifest, and compiler controls. It never scans the repository for a similar
filename or package name after a legitimate resolution path fails.

### Superseded import plan

`docs/plans/2026-07-01-import-dependency-graph.md` remains useful extraction
research, but Stage 6 superseded its storage and public API. Stage 8 keeps the
accepted `index.json.graph` import records, `loci:imports` edges, service API,
and `loci_graph_imports` MCP tool. It does not add the old top-level import
store, import CLI, or best-effort Go/Rust filename mapping.

The old plan explicitly deferred `paths`, `baseUrl`, package managers, dynamic
imports, and module-aware Go/Rust. Stage 7 completed Go. This plan takes the
JavaScript/TypeScript configuration portion out of deferral under the current
generic graph contracts.

## Official Semantics Used

Implementation is grounded in primary documentation:

- [TypeScript module-resolution reference](https://www.typescriptlang.org/docs/handbook/modules/reference)
  defines extension substitution, `paths` precedence and wildcards, `baseUrl`,
  package `exports`/`imports`, condition selection, and Node/bundler mode
  differences.
- [TypeScript `extends`](https://www.typescriptlang.org/tsconfig/extends.html)
  defines base-first override behavior, origin-relative paths, and forbidden
  cycles.
- [TypeScript `moduleResolution`](https://www.typescriptlang.org/tsconfig/moduleResolution.html)
  distinguishes `node16`/`nodenext`, `bundler`, `node10`, and obsolete
  `classic` behavior.
- [TypeScript `paths`](https://www.typescriptlang.org/tsconfig/paths.html) and
  [`baseUrl`](https://www.typescriptlang.org/tsconfig/baseUrl.html) confirm that
  aliases affect compiler lookup but do not rewrite emitted imports, and that
  `baseUrl` precedes package lookup.
- [TypeScript `rootDirs`](https://www.typescriptlang.org/tsconfig/rootDirs.html)
  defines virtual directory merging; [TypeScript `moduleSuffixes`](https://www.typescriptlang.org/tsconfig/moduleSuffixes.html)
  defines platform-suffix ordering.
- [TypeScript `customConditions`](https://www.typescriptlang.org/tsconfig/customConditions.html),
  [`resolvePackageJsonExports`](https://www.typescriptlang.org/tsconfig/resolvePackageJsonExports.html),
  and [`resolvePackageJsonImports`](https://www.typescriptlang.org/tsconfig/resolvePackageJsonImports.html)
  define when package maps participate.
- [Node package documentation](https://nodejs.org/api/packages.html) defines
  package scopes, `type`, `main`, `exports`, `imports`, self-reference,
  encapsulation, subpath patterns, target containment, and condition object
  order.
- [Node ECMAScript modules](https://nodejs.org/api/esm.html) requires explicit
  relative extensions and directory entries for ESM requests.
- [npm workspaces](https://docs.npmjs.com/cli/using-npm/workspaces/) defines
  package-json workspace membership and name-based consumption.
- [pnpm workspaces](https://pnpm.io/workspaces) and
  [`pnpm-workspace.yaml`](https://pnpm.io/pnpm-workspace_yaml) define workspace
  roots, include/exclude patterns, the always-included root package, and the
  `workspace:` protocol.
- [Bun workspaces](https://bun.sh/docs/pm/workspaces) confirms that the standard
  package-json workspace form and `workspace:` declarations are also current
  outside npm/pnpm.

Where these tools differ or depend on runtime/install state, Stage 8 narrows to
the shared repository evidence rather than choosing one ambient host behavior.

## Live Implementation Baseline

Loci inspection on 2026-07-18 established:

- `src/loci/parser/languages.py` indexes only `.ts`, `.tsx`, and `.js` from the
  JavaScript/TypeScript extension family.
- `src/loci/parser/imports.py` extracts static `import_statement` and
  source-bearing `export_statement` observations and already preserves
  TypeScript `type_only` and re-export flags.
- `src/loci/graph/imports.py` recognizes `.ts`, `.tsx`, and `.js`, resolves only
  `./` and `../`, and tries exactly:
  `p.ts`, `p.tsx`, `p.js`, `p/index.ts`, `p/index.tsx`, `p/index.js`.
- Every JavaScript/TypeScript bare specifier currently returns
  `unresolved_reason="external"`.
- `RepositoryScan` discovers source files plus `go.mod`/`go.work`; it does not
  surface JavaScript controls.
- `materialize_graph()` accepts raw imports and an optional Go package index;
  it has no JavaScript resolution context.
- `ImportRecord` is strict and has no resolution-basis or control-provenance
  fields.
- `graph_imports()` and `loci_graph_imports` already expose stable pagination,
  status filtering, target kind, evidence text, and unresolved reasons.
- persisted graph state is schema 3; the top-level extractor version is 6.
- graph health currently reports 720 edges, 347 import observations, 160
  resolved observations, and 187 unresolved observations for Loci's live
  index.

The accepted API baseline is additive. Existing Python and Go resolution and
all graph retrieval surfaces must remain semantically unchanged.

## Supported Contract

### Source extensions

Stage 8 indexes and parses:

| Language | Extensions |
| --- | --- |
| TypeScript | `.ts`, `.tsx`, `.mts`, `.cts` |
| JavaScript | `.js`, `.jsx`, `.mjs`, `.cjs` |

Declaration forms `.d.ts`, `.d.mts`, and `.d.cts` are naturally included by
their final suffix. Existing test-file and skip-directory policies remain
unchanged.

### Observation kinds

Stage 8 resolves the observations Stage 6 already extracts:

- static ECMAScript imports, including side-effect imports;
- TypeScript type-only imports;
- source-bearing runtime re-exports; and
- source-bearing type-only re-exports.

Literal `import()` expressions, `require()` calls, framework-specific loaders,
and non-literal specifiers remain out of scope. A JavaScript `require` identifier
can be rebound, so treating every call as a trusted dependency would require
scope analysis. Dynamic-import execution is conditional and needs an additive
observation-kind contract. Those are later extraction changes, not silent
extras in this resolver stage.

### Control files

The root scan surfaces these contained, non-symlink candidates:

- every `package.json` outside existing skipped directories;
- every `pnpm-workspace.yaml` outside existing skipped directories;
- every standard `tsconfig.json` and `jsconfig.json`; and
- local `.json` files reached through a supported config `extends` path.

Custom entry configs such as `tsconfig.build.json` are not assumed active just
because they exist. They participate only when reached by a supported local
`extends` chain. Loci cannot know that a script runs `tsc -p
tsconfig.build.json` without executing or interpreting the script.

### Workspace discovery

Supported workspace declarations are:

- a package-json `workspaces` array; and
- a pnpm workspace `packages` array, with pnpm's root package always included.

The bounded glob subset is repository-relative literal path components, `*`,
terminal or component `**`, and leading `!` exclusions for pnpm. Backslashes,
absolute paths, `..`, braces, extglobs, character classes, and more than one
semantic wildcard capture are rejected as unsupported configuration.

Patterns match only already discovered package-manifest directories. They do
not launch another unbounded filesystem traversal.

A workspace package must have a valid non-empty `name`. Package ownership uses
the deepest active package root containing a source file. Duplicate active
package names, overlapping workspace definitions that disagree, or two equally
specific owners are ambiguous and produce no trusted edge.

For an import from package A to workspace package B:

- B must be an active workspace member with a unique matching package name;
- A's owning manifest must declare B's import name in `dependencies`,
  `devDependencies`, `peerDependencies`, or `optionalDependencies`; and
- self-references and local `#imports` mappings are exempt from that dependency
  declaration because their own package controls are the authority.

The declaration value must be a non-empty string. Stage 8 records declared
repository dependency intent; it does not evaluate every npm semver range or
claim a lockfile-specific installed version. Alias forms whose dependency key
does not equal the target workspace package name are left unresolved in this
stage.

### Compiler-project ownership

Automatic config ownership is deterministic:

1. TypeScript-family sources consider standard `tsconfig.json` files.
2. JavaScript-family sources prefer a standard `jsconfig.json` at a given
   directory; otherwise they may use a `tsconfig.json` whose effective options
   enable JavaScript.
3. The deepest ancestor config whose effective `files`/`include`/`exclude`
   selection contains the source wins.
4. Two equally specific applicable configs are ambiguous.
5. If no config applies, Loci retains the accepted Stage 6 compatibility mode.

Supported membership patterns use the same bounded repository-relative glob
engine as workspace discovery. `files`, `include`, and `exclude` preserve
TypeScript's replace-on-inheritance behavior. The default selection is supported
source files below the config directory, excluding existing skip directories
and the effective `outDir`.

`references` are parsed only for validation and provenance; they are not used
to guess which custom project a command selected. A solution config with no
owned files does not apply aliases to every descendant by accident.

### Config inheritance and options

Supported `extends` values are contained relative strings resolving to a file,
an added `.json` suffix, or a directory's `tsconfig.json`. Package-based extends,
absolute paths, URLs, and symlinks are unsupported. Base options load first;
child options override them. Relative option paths retain the directory of the
config that declared that option. Cycles or chains deeper than the fixed limit
invalidate the affected config.

Stage 8 understands these resolution-affecting compiler options:

- `module` and `moduleResolution`;
- `paths` and `baseUrl`;
- `rootDirs` and `moduleSuffixes`;
- `customConditions`;
- `resolvePackageJsonExports` and `resolvePackageJsonImports`;
- `rootDir`, `outDir`, and `declarationDir` for contained local output-to-input
  remapping; and
- `allowJs`, `files`, `include`, and `exclude` for project ownership.

`paths` supports exact keys or one `*`, chooses the longest literal prefix, and
tries mapped values in declared order. A mapped value becomes a repository
path lookup; it does not trigger package `exports` behavior. `baseUrl` runs
after `paths` and before workspace package lookup. Both must resolve to an
indexed contained file.

`rootDirs` tries the source's virtual relative suffix under the other declared
roots in order. `moduleSuffixes` applies each declared suffix in order; an empty
suffix must be present to try the unsuffixed file.

Resolution-mode normalization is frozen: explicit `node` normalizes to
`node10`; explicit `node16`, `nodenext`, `bundler`, `node10`, or `classic` is
retained. When `moduleResolution` is absent, `module: node16|node18|node20`
implies the `node16` resolver, `module: nodenext` implies `nodenext`, and
`module: preserve` implies `bundler`. Other absent-mode combinations use the
documented compatibility/unknown-mode convergence rules instead of guessing a
moving compiler default. This is required for Anvil, whose current config sets
`module: "nodenext"` without repeating `moduleResolution`.

Unknown compiler options that do not affect module resolution are ignored.
Known resolution-changing features outside this contract, such as plugins or
package-based config inheritance, produce an
`unsupported_configuration` result when they could change the observed import.

### Resolution precedence

For each JavaScript/TypeScript observation, the resolver applies:

1. validate the specifier and classify URLs, `node:` built-ins, and proven
   remote dependencies as external;
2. resolve `./` or `../` with the effective project mode, extension
   substitution, `moduleSuffixes`, and then `rootDirs`;
3. for non-relative specifiers, try effective `paths`;
4. try effective `baseUrl`;
5. for `#` specifiers, try the owning package's enabled `imports` map;
6. for the owning package's own name, try enabled self-reference through
   `exports`;
7. try a uniquely declared active workspace package by name; and
8. otherwise report external.

There is no subsequent filename, directory-name, symbol-name, or global
repository search.

### File candidate rules

An explicitly written source extension first attempts that exact indexed file.
JavaScript output extensions use TypeScript-style source substitution:

| Requested family | Runtime/source candidates |
| --- | --- |
| `.js` or `.jsx` | `.ts`, `.tsx`, `.js`, `.jsx`; add `.d.ts` before JS only for a type-only observation |
| `.mjs` | `.mts`, `.mjs`; add `.d.mts` before `.mjs` for a type-only observation |
| `.cjs` | `.cts`, `.cjs`; add `.d.cts` before `.cjs` for a type-only observation |

Extensionless and directory-index lookup is allowed only in Stage 6
compatibility mode, `bundler`, `node10`/CommonJS request mode, compiler aliases
whose effective mode allows it, or a package legacy entry lookup. Its runtime
order preserves the existing winners before adding `.jsx`:

~~~text
p.ts, p.tsx, p.js, p.jsx,
p/index.ts, p/index.tsx, p/index.js, p/index.jsx
~~~

Type-only observations insert `p.d.ts` before `p.js` and `p/index.d.ts` before
`p/index.js`. TypeScript never treats omitted `.mts`/`.mjs` or `.cts`/`.cjs`
extensions as implicit candidates, so Stage 8 does not either.

Under a proven ESM `node16`/`nodenext` request, a relative import must include a
supported extension and a directory index must be written explicitly. This
matches Node's mandatory-extension contract. An absent config retains Stage 6
relative behavior for backward compatibility.

### Package `exports`, `imports`, and entry points

Supported package maps include:

- root string sugar;
- exact root and subpath keys;
- one-`*` subpath patterns;
- nested condition objects, evaluated in source JSON key order;
- `null` blocks; and
- contained `./` string targets without `..`, `node_modules`, encoded
  separators, absolute paths, or symlink escape.

Arrays and versioned `types@...` conditions are deliberately unsupported in
Stage 8 because their fallback/version semantics require more host state than
this graph records. Encountering one on the selected path fails closed with
`unsupported_configuration`.

The request mode is determined as follows:

- `.mts`/`.mjs` static imports use `import`;
- `.cts`/`.cjs` static imports use `require` semantics where TypeScript permits
  their emitted form;
- `bundler` uses `import` for the observations in scope;
- `node10` uses legacy CommonJS lookup;
- `node16`/`nodenext` use file extension plus nearest package `type` and
  effective `module`; and
- if the repository does not prove `import` versus `require`, both are
  evaluated and resolution succeeds only when they converge on the same
  indexed file.

Normal observations match effective custom conditions, `node` where the mode
requires it, `import` or `require`, and `default`. Type-only observations also
admit `types`. Because package-map object order is significant, the first key
whose condition is active wins.

The mere presence of enabled `exports` encapsulates the package: an unexported
subpath is `inaccessible` and never falls back to a package-relative file.
`imports` applies only within its owning package. External targets reached from
an `imports` map remain external unless they independently satisfy the active
workspace contract.

When `exports` is absent or explicitly disabled by the effective compiler
mode, package-root lookup uses:

- type-only: `types`, then `typings`, then `main`, then index candidates;
- runtime: `main`, then index candidates; and
- subpath: package-relative file rules.

Non-standard `module`, `browser`, framework, import-map, and bundler plugin
fields are not interpreted.

### Generated output remapping

For a local package self-reference or `#imports` target, Loci may map a target
under effective `outDir` or `declarationDir` back under effective `rootDir` only
when all three paths are contained, the mapping is one-to-one, and the mapped
source file exists in the index. Output extensions map only through the official
families (`.js` to `.ts`/`.tsx`, `.mjs`/`.d.mts` to `.mts`, `.cjs`/`.d.cts` to
`.cts`).

This remapping is not guessed across workspace package boundaries. If package B
exports only missing `dist` output, an import from package A remains
`not_indexed`; Loci does not pretend B's arbitrary `src` file is the entry.

## Deliberate Non-goals

Stage 8 does not:

- inspect or index installed `node_modules`;
- read global package stores, npm caches, Yarn PnP archives, or ambient import
  maps;
- parse npm, pnpm, Yarn, or Bun lockfiles;
- execute Node, TypeScript, npm, pnpm, Yarn, Bun, a bundler, a generator, a
  package script, a test, or repository code;
- use the network or registry metadata;
- implement arbitrary loader hooks, bundler aliases, TypeScript plugins,
  `NODE_PATH`, package manager overrides, or framework virtual modules;
- resolve JSON, CSS, images, native addons, Vue/Svelte modules, or generated
  files that Loci does not index;
- treat a declaration-only package target as runtime implementation evidence;
- create JavaScript package nodes or change existing JavaScript file-target
  semantics;
- resolve dynamic imports or shadowable `require()` calls;
- resolve imported symbols, references, calls, or re-export chains to original
  declarations;
- change Python, Go, Rust, Markdown, graph profile, contribution, search,
  outline, traversal, or anchor behavior;
- add a JavaScript-specific MCP tool or import CLI; or
- run a model, judge, or wiki audit as part of indexing or review.

## Threat Model and Bounds

The repository and all controls are untrusted input. Stage 8 must prevent:

- a manifest, config, workspace pattern, package target, or `extends` path from
  reading outside the repository;
- symlinked controls or targets from reaching host files;
- JSON/JSONC/YAML alias, nesting, wildcard, condition, config-cycle, or
  candidate explosion from consuming unbounded time or memory;
- duplicate JSON keys from changing meaning across parsers;
- malformed controls from leaving a partial graph that looks trusted;
- absolute host paths or sensitive file contents from leaking through
  diagnostics; and
- any repository text from reaching a shell, runtime, package manager, network
  client, or model.

Frozen bounds:

~~~python
MAX_JAVASCRIPT_CONTROL_BYTES = 1_048_576
MAX_JAVASCRIPT_CONTROL_FILES = 10_000
MAX_JAVASCRIPT_JSON_DEPTH = 64
MAX_JAVASCRIPT_WORKSPACE_PATTERNS = 1_000
MAX_JAVASCRIPT_WORKSPACE_PACKAGES = 10_000
MAX_TYPESCRIPT_CONFIG_EXTENDS_DEPTH = 32
MAX_TYPESCRIPT_PATH_PATTERNS = 1_000
MAX_TYPESCRIPT_PATH_TARGETS = 10_000
MAX_JAVASCRIPT_PACKAGE_MAP_DEPTH = 32
MAX_JAVASCRIPT_RESOLUTION_CANDIDATES = 256  # per observation
~~~

Crossing a whole-context limit rejects that JavaScript resolution context
rather than truncating it into a plausible partial result. Source indexing and
other languages continue, graph health degrades with a bounded warning, and
affected imports remain unresolved.

All control reads use lexical normalization, `lstat`, real-path containment,
non-symlink regular-file checks, byte ceilings, strict UTF-8, duplicate-key
rejection, finite JSON values, and bounded diagnostics. `package.json` is
strict JSON. TypeScript config parsing uses a bounded JSONC lexical pass that
removes comments and trailing commas only outside strings before the same
strict JSON decoder. pnpm YAML uses the existing safe YAML dependency with
aliases/merge keys rejected and only the `packages` scalar-list shape admitted.

## Exact Internal APIs

### New JavaScript module subsystem

Add `src/loci/graph/javascript_modules.py` with these public-to-Loci contracts:

~~~python
JavaScriptResolutionBasis: TypeAlias = Literal[
    "relative_path",
    "compiler_paths",
    "compiler_base_url",
    "compiler_root_dirs",
    "package_imports",
    "package_self_reference",
    "workspace_exports",
    "workspace_legacy_entry",
]

JavaScriptModuleProblemCode: TypeAlias = Literal[
    "GRAPH_JAVASCRIPT_PACKAGE_INVALID",
    "GRAPH_JAVASCRIPT_WORKSPACE_INVALID",
    "GRAPH_TYPESCRIPT_CONFIG_INVALID",
    "GRAPH_JAVASCRIPT_INDEX_LIMIT_EXCEEDED",
]

@dataclass(frozen=True, slots=True)
class JavaScriptPackageManifest:
    source: str
    root: str
    name: str | None
    package_type: Literal["module", "commonjs"] | None
    workspaces: tuple[str, ...]
    dependencies: Mapping[str, str]
    dev_dependencies: Mapping[str, str]
    peer_dependencies: Mapping[str, str]
    optional_dependencies: Mapping[str, str]
    main: str | None
    types: str | None
    typings: str | None
    has_exports: bool
    exports: JSONValue
    has_imports: bool
    imports: JSONValue

@dataclass(frozen=True, slots=True)
class TypeScriptPathMapping:
    pattern: str
    targets: tuple[str, ...]  # normalized repository-relative patterns

@dataclass(frozen=True, slots=True)
class TypeScriptProjectConfig:
    source: str
    root: str
    controls: tuple[str, ...]
    module: str | None
    module_resolution: Literal[
        "node16", "nodenext", "bundler", "node10", "classic"
    ] | None
    allow_js: bool
    paths: tuple[TypeScriptPathMapping, ...]
    base_url: str | None
    root_dirs: tuple[str, ...]
    module_suffixes: tuple[str, ...] | None
    custom_conditions: tuple[str, ...]
    resolve_package_json_exports: bool | None
    resolve_package_json_imports: bool | None
    root_dir: str | None
    out_dir: str | None
    declaration_dir: str | None
    files: tuple[str, ...] | None
    include: tuple[str, ...] | None
    exclude: tuple[str, ...] | None
    unsupported_resolution_options: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class JavaScriptWorkspace:
    source: str
    root: str
    package_roots: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class JavaScriptModuleProblem:
    code: JavaScriptModuleProblemCode
    message: str
    source: str
    details: dict[str, JSONValue]

@dataclass(frozen=True, slots=True)
class JavaScriptModuleContext:
    manifests: tuple[JavaScriptPackageManifest, ...]
    workspaces: tuple[JavaScriptWorkspace, ...]
    configs: tuple[TypeScriptProjectConfig, ...]

@dataclass(frozen=True, slots=True)
class JavaScriptModuleLoad:
    context: JavaScriptModuleContext
    input_hashes: dict[str, str]
    problems: tuple[JavaScriptModuleProblem, ...]

@dataclass(frozen=True, slots=True)
class JavaScriptResolutionIndex:
    # Frozen normalized lookup maps; no repository I/O during resolution.
    context: JavaScriptModuleContext
    indexed_files: frozenset[str]
    manifests_by_root: Mapping[str, JavaScriptPackageManifest]
    active_packages_by_name: Mapping[str, tuple[JavaScriptPackageManifest, ...]]
    package_owner_by_file: Mapping[str, JavaScriptPackageManifest]
    config_by_file: Mapping[str, TypeScriptProjectConfig]

@dataclass(frozen=True, slots=True)
class JavaScriptResolutionBuild:
    index: JavaScriptResolutionIndex
    problems: tuple[JavaScriptModuleProblem, ...]

@dataclass(frozen=True, slots=True)
class JavaScriptImportResolution:
    target_file: str | None
    basis: JavaScriptResolutionBasis | None
    control_files: tuple[str, ...]
    unresolved_reason: ImportUnresolvedReason | None

def load_javascript_module_context(
    repo_path: Path,
    control_candidates: Sequence[Path],
) -> JavaScriptModuleLoad: ...

def build_javascript_resolution_index(
    context: JavaScriptModuleContext,
    *,
    file_nodes: Mapping[str, Symbol],
) -> JavaScriptResolutionBuild: ...

def resolve_javascript_import(
    raw: RawImport,
    index: JavaScriptResolutionIndex,
) -> JavaScriptImportResolution: ...
~~~

`has_exports` and `has_imports` distinguish an absent field from an explicit
`null` block. Effective config paths and patterns are normalized to
repository-relative form while loading, so the pure resolver never needs an
ambient config directory. The loader is the only repository-I/O layer. The
builder and resolver are pure. Dataclass fields persisted or exposed publicly
are validated and allowlisted; raw manifest/config objects are not copied into
graph state or diagnostics.

`JavaScriptImportResolution` requires exactly one of `target_file` and
`unresolved_reason`: a resolved result has a target, basis, and null reason; an
unresolved result has no target or basis and carries one admitted reason.

### Import contracts

Extend `ImportUnresolvedReason` with exactly:

~~~python
"unsupported_configuration"
~~~

Existing reason meanings remain:

| Reason | Stage 8 meaning |
| --- | --- |
| `external` | builtin, URL, remote/uninstalled package, undeclared workspace package, or no repository-local route |
| `not_indexed` | a valid contained mapping identifies a path, but no supported indexed file is there |
| `ambiguous` | equally valid configs, workspace identities, request modes, or targets disagree |
| `invalid_specifier` | malformed, absolute, escaping, encoded-separator, or otherwise invalid specifier |
| `inaccessible` | package encapsulation, private import scope, or blocked/null export forbids the path |
| `unsupported_configuration` | selected repository controls use semantics outside the frozen subset |

Extend `ImportRecord` with:

~~~python
resolution_basis: JavaScriptResolutionBasis | None
resolution_control_files: tuple[str, ...]
~~~

Invariants:

- resolved JavaScript/TypeScript records require a non-null basis;
- relative resolution without controls uses `relative_path` and an empty tuple;
- every control path is normalized, repository-relative, unique, and sorted;
- unresolved records have no basis but may list the controls that explain the
  failure;
- Python, Go, and Rust records use `None` and `()`; and
- the fields round-trip strictly in graph state.

Change resolver signatures additively:

~~~python
def resolve_import(
    raw: RawImport,
    *,
    file_nodes: Mapping[str, Symbol],
    go_packages: GoPackageIndex | None = None,
    javascript_modules: JavaScriptResolutionIndex | None = None,
) -> ImportRecord: ...

def resolve_imports(
    raw_imports: Sequence[RawImport],
    *,
    file_nodes: Mapping[str, Symbol],
    go_packages: GoPackageIndex | None = None,
    javascript_modules: JavaScriptResolutionIndex | None = None,
) -> list[ImportRecord]: ...
~~~

When `javascript_modules` is omitted, direct unit/API callers receive an empty
control context with the accepted Stage 6 relative behavior. Python and Go
call behavior remains byte-for-byte compatible.

### Materialization

Change `materialize_graph()` additively:

~~~python
def materialize_graph(
    repo_path: Path,
    symbols: Sequence[Symbol],
    file_hashes: Mapping[str, str],
    profiles: Sequence[LoadedGraphProfile],
    contributions: Sequence[LoadedGraphContribution],
    *,
    raw_imports: Sequence[RawImport] = (),
    go_packages: GoPackageIndex | None = None,
    javascript_modules: JavaScriptResolutionIndex | None = None,
    input_hashes: Mapping[str, str] | None = None,
    diagnostics: Sequence[GraphDiagnostic] = (),
) -> GraphIndexState: ...
~~~

Import edge shape does not change:

~~~json
{
  "from": "apps/web/src/page.ts::__file__#file",
  "to": "packages/core/src/format.ts::__file__#file",
  "type": "imports",
  "directed": true,
  "namespace": "loci",
  "resolution": "import-resolved",
  "evidence": {
    "file": "apps/web/src/page.ts",
    "line": 1,
    "content_hash": "sha256-of-importing-source"
  }
}
~~~

The import statement remains the edge evidence. The import record supplies the
additional control provenance, and every control hash participates in index
freshness.

### Service and MCP API

`graph_imports()` keeps its exact input signature:

~~~python
def graph_imports(
    repo: str | Path,
    *,
    file: str | None = None,
    status: Literal["all", "resolved", "unresolved"] = "all",
    offset: int = 0,
    limit: int = 100,
    ensure_fresh: bool = False,
) -> dict[str, Any]: ...
~~~

Each item adds only:

~~~json
{
  "resolution_basis": "workspace_exports",
  "resolution_control_files": [
    "apps/web/package.json",
    "package.json",
    "packages/core/package.json"
  ]
}
~~~

All existing item fields, counts, pagination, ordering, status semantics, and
schema version remain. `GRAPH_SCHEMA_VERSION` remains 1 because this is an
additive response field change, consistent with Stage 7's additive target
fields.

`loci_graph_imports` keeps its exact MCP inputs and gains the same two item
fields. There is no new tool and no CLI surface.

### Persistence versions

- bump `GRAPH_STATE_SCHEMA_VERSION` from 3 to 4 because strict import-record
  fields change;
- bump `EXTRACTOR_VERSION` from 6 to 7 because the indexed extension set
  changes;
- keep `INDEX_SCHEMA_VERSION` at 5 and `GRAPH_SCHEMA_VERSION` at 1; and
- force a full rebuild for any old extractor or graph-state version before the
  new fields are read.

No compatibility shim will fabricate resolution provenance for an old record.

## Indexing and Freshness Flow

`RepositoryScan` becomes:

~~~python
@dataclass(frozen=True, slots=True)
class RepositoryScan:
    indexable_files: tuple[tuple[Path, str, str], ...]
    go_control_candidates: tuple[Path, ...]
    javascript_control_candidates: tuple[Path, ...]
~~~

`index_repo()` performs, in order:

1. one sorted root scan for indexable sources plus Go and JavaScript controls;
2. bounded Go control loading;
3. bounded JavaScript control loading;
4. graph extension loading;
5. normal source parsing/reuse and static import extraction;
6. Go package-index construction;
7. JavaScript resolution-index construction from current file nodes;
8. graph materialization with both language indexes; and
9. one atomic store replacement after all graph validation succeeds.

Graph input hashes merge graph extensions, Go controls, and every JavaScript
control read or rejected with a stable sentinel. Add/change/delete of a
manifest, workspace file, standard config, or locally extended config changes
freshness and re-resolves unchanged imports. Invalid controls persist their
hash plus warning so `ensure_fresh_index()` does not loop forever.

Source target add/delete already changes top-level file hashes and therefore
re-resolves retained observations. Full and incremental indexes must serialize
identically.

Normal unresolved imports do not degrade graph health. Invalid, ambiguous, or
limit-rejected control contexts do, through bounded diagnostics:

- `GRAPH_JAVASCRIPT_PACKAGE_INVALID`
- `GRAPH_JAVASCRIPT_WORKSPACE_INVALID`
- `GRAPH_TYPESCRIPT_CONFIG_INVALID`
- `GRAPH_JAVASCRIPT_INDEX_LIMIT_EXCEEDED`

Diagnostics identify only repository-relative controls, reason codes, lines
where cheaply available, and numeric limits. They never echo arbitrary control
values, host paths, or file contents.

## Exact File Changes

| File | Change |
| --- | --- |
| `src/loci/graph/javascript_modules.py` | New bounded control loader, workspace/config builder, and pure resolver |
| `src/loci/parser/languages.py` | Register `.jsx`, `.mjs`, `.cjs`, `.mts`, `.cts` |
| `src/loci/parser/imports.py` | Add `unsupported_configuration`; preserve static extraction contract |
| `src/loci/graph/imports.py` | Add record provenance, thread JavaScript index, remove relative-only resolver ownership |
| `src/loci/graph/materialize.py` | Thread JavaScript resolution index into import materialization |
| `src/loci/graph/contracts.py` | Bump persisted graph-state schema to 4 only |
| `src/loci/graph/state.py` | Strictly round-trip expanded import records through existing state machinery |
| `src/loci/service.py` | Discover/load/hash controls, build index, merge diagnostics, preserve one root scan |
| `src/loci/storage/index_store.py` | Bump extractor version to 7 |
| `tests/graph/test_javascript_modules.py` | New loader, config, workspace, package-map, safety, bound, and pure resolution tests |
| `tests/parser/test_imports.py` | Static extraction across all new source extensions |
| `tests/parser/test_extractor.py` | New extensions produce normal file/symbol nodes |
| `tests/graph/test_imports.py` | Record invariants, candidate ordering, bases, unresolved reasons, Python/Go regressions |
| `tests/graph/test_materialize.py` | Directed exact edges and control-aware materialization |
| `tests/graph/test_state.py` | Schema-4 record round trips and strict failures |
| `tests/storage/test_index_store.py` | Version rebuild and persisted control provenance |
| `tests/test_service.py` | End-to-end indexing, freshness, incremental, diagnostics, counts, and API compatibility |
| `tests/test_mcp_server.py` | Fresh-process additive MCP response and unchanged inputs |
| `README.md` | Supported JS/TS controls, extensions, guarantees, and limitations |
| `skills/loci/SKILL.md` | Agent-facing capability and trust boundary |
| `docs/design/2026-07-13-extensible-graph-retrieval-design.md` | Mark Stage 8 accepted/implemented only after gates pass; keep Rust next |
| `docs/reviews/2026-07-18-extensible-graph-retrieval-stage-8-final-review.md` | New final evidence packet created during implementation |

No benchmark fixture, llm-wiki source, Anvil source, lockfile, package manifest,
or generated output is modified.

## Incremental Implementation Tasks

Every task begins with focused failing tests, ends green, and is committed as a
reviewable slice only after its local gate passes. No task touches more than
five implementation/test files at once.

### Task 1 — Control loader and safety shell

Files:

- new `src/loci/graph/javascript_modules.py`
- new `tests/graph/test_javascript_modules.py`

Add strict package JSON, bounded JSONC, restricted pnpm YAML, control hashes,
problem contracts, containment, symlink rejection, duplicate-key rejection,
limits, deterministic ordering, local `extends`, and cycle detection. No import
resolves yet.

Gate:

~~~sh
uv run pytest -q tests/graph/test_javascript_modules.py
~~~

### Task 2 — Full extension family

Files:

- `src/loci/parser/languages.py`
- `tests/parser/test_imports.py`
- `tests/parser/test_extractor.py`
- `src/loci/storage/index_store.py`
- `tests/storage/test_index_store.py`

Register the extension family, prove static extraction and normal indexing, and
bump extractor version 7 so old indexes cannot silently omit new files.

Gate:

~~~sh
uv run pytest -q tests/parser/test_imports.py tests/parser/test_extractor.py tests/storage/test_index_store.py
~~~

### Task 3 — Pure config/workspace/package resolution

Files:

- `src/loci/graph/javascript_modules.py`
- `tests/graph/test_javascript_modules.py`

Build project/package ownership and implement the frozen precedence, candidate,
condition, encapsulation, remapping, and unresolved rules. Add adversarial
candidate-count and ambiguity tests. No service wiring yet.

Gate:

~~~sh
uv run pytest -q tests/graph/test_javascript_modules.py
~~~

### Task 4 — Import record and resolver integration

Files:

- `src/loci/parser/imports.py`
- `src/loci/graph/imports.py`
- `tests/graph/test_imports.py`
- `src/loci/graph/state.py`
- `tests/graph/test_state.py`

Add the unresolved reason and provenance fields, thread the JavaScript index,
preserve default relative callers, and prove strict serialization plus unchanged
Python/Go behavior.

Gate:

~~~sh
uv run pytest -q tests/graph/test_imports.py tests/graph/test_state.py
~~~

### Task 5 — Materialization and persisted schema

Files:

- `src/loci/graph/materialize.py`
- `src/loci/graph/contracts.py`
- `tests/graph/test_materialize.py`
- `tests/storage/test_index_store.py`

Thread the JavaScript index, bump graph state to 4, and prove edge evidence,
type-only edge kinds, atomic validation, old-state rebuild, and fresh-process
round trips.

Gate:

~~~sh
uv run pytest -q tests/graph/test_materialize.py tests/storage/test_index_store.py
~~~

### Task 6 — Service, freshness, and diagnostics

Files:

- `src/loci/service.py`
- `tests/test_service.py`

Extend the one-pass scan, load/build the context, merge hashes and diagnostics,
and prove control add/change/delete, target add/delete, unchanged-source
re-resolution, full/incremental equality, graph health, stable API ordering, and
no source-navigation loss on bad controls.

Gate:

~~~sh
uv run pytest -q tests/test_service.py
~~~

### Task 7 — MCP and user/agent documentation

Files:

- `tests/test_mcp_server.py`
- `README.md`
- `skills/loci/SKILL.md`
- `docs/design/2026-07-13-extensible-graph-retrieval-design.md`

Prove fresh-process MCP output, document exact supported and unsupported
semantics, and update roadmap status only after implementation evidence exists.
The MCP server implementation should require no signature change; if a change
becomes necessary, stop for owner review rather than expanding this task.

Gate:

~~~sh
uv run pytest -q tests/test_mcp_server.py
~~~

### Task 8 — Final verification and review packet

Files:

- new `docs/reviews/2026-07-18-extensible-graph-retrieval-stage-8-final-review.md`

Run the full evidence matrix below, inspect Anvil, record compatibility and
limitations, verify repository/remote state, and present the owner gate. The
implementation is not called accepted until the owner approves this packet.

## Required Test Matrix

### Loader and security

Prove:

1. strict package JSON and JSONC comments/trailing commas parse deterministically;
2. duplicate keys, invalid UTF-8, non-finite values, excessive depth, and wrong
   field shapes fail whole controls;
3. symlinked, absolute, escaping, oversized, and post-`lstat` growth controls
   cannot be read;
4. local `extends` preserves base-first overrides and each option's path origin;
5. config cycles, excessive depth, package extends, and ambiguous ownership
   produce bounded problems;
6. pnpm aliases/merge keys and unsupported YAML shapes are rejected;
7. count limits reject whole contexts rather than truncating; and
8. diagnostics contain no absolute host path or arbitrary control value.

### Relative and extension resolution

Prove:

1. all eight source extensions index and parse;
2. accepted `.ts`/`.tsx`/`.js` no-config winner order remains unchanged;
3. `.jsx` extends the legacy family without moving earlier winners;
4. explicit `.js`, `.mjs`, and `.cjs` substitute only their documented source
   families;
5. type-only candidates prefer declarations at the documented points;
6. `.mts`/`.mjs` and `.cts`/`.cjs` are never guessed from extensionless paths;
7. ESM Node mode rejects extensionless relative and directory imports;
8. CommonJS/bundler/compatibility modes admit their documented candidates;
9. `rootDirs` and `moduleSuffixes` preserve declared order; and
10. repository escape, backslash, encoded separator, URL, and builtin cases
    remain non-edges.

### Compiler aliases

Prove:

1. exact `paths`, one-star substitution, longest-prefix selection, and target
   fallback order;
2. path value origin with inherited configs and optional `baseUrl`;
3. `paths` precedes `baseUrl`, and both precede packages;
4. aliases resolve only contained indexed files and never invoke package maps;
5. project membership prevents an unrelated config from supplying an alias;
6. same-depth applicable configs are ambiguous; and
7. unsupported resolution-changing config fails closed without affecting
   Python/Go or symbol navigation.

### Workspaces and package maps

Prove:

1. package-json workspace arrays and pnpm include/exclude patterns;
2. pnpm root inclusion and nearest nested workspace ownership;
3. source package dependency declarations across all four admitted fields;
4. undeclared, inactive, duplicate-name, and aliased dependencies do not become
   trusted edges;
5. exact exports, root sugar, subpaths, one-star patterns, null blocks, and
   encapsulation;
6. `imports` is private to the owner and self-reference requires the owner name
   plus exports;
7. import/require/custom/default/type condition order and unknown-mode
   convergence versus ambiguity;
8. target path containment and invalid `node_modules`/escape segments;
9. legacy `main`/`types`/`typings`/index and package-relative subpaths when
   exports does not apply;
10. missing build output is `not_indexed` with no source guess; and
11. contained self/import output remapping works only with a one-to-one
    rootDir/outDir declaration.

### Persistence, service, and compatibility

Prove:

1. graph-state schema 4 and extractor 7 force a full rebuild;
2. record provenance survives serialization and a fresh process;
3. full and incremental serialized indexes match;
4. source and control add/change/delete re-resolve unchanged observations;
5. invalid controls reach stable degraded health without refresh loops;
6. resolved records emit one directed file-to-file edge with import evidence;
7. unresolved records emit no edge and remain paginated/inspectable;
8. `graph_imports` existing filters, counts, order, pagination, and input
   validation are unchanged;
9. `loci_graph_imports` input schema is unchanged and two output fields are
   additive;
10. Python and Go records/edges are byte-equivalent except for new null/empty
    stored provenance fields required by schema 4;
11. Rust remains `unresolved/unsupported_language`;
12. search, outline, get, grep, graph health, neighbours, paths, retrieval,
    Markdown profiles, and contributions retain behavior; and
13. the repository root is traversed once for source and control discovery.

## Verification Commands

Focused gates run throughout. Final local verification is:

~~~sh
uv run pytest -q tests/graph/test_javascript_modules.py
uv run pytest -q tests/parser/test_imports.py tests/parser/test_extractor.py
uv run pytest -q tests/graph/test_imports.py tests/graph/test_materialize.py tests/graph/test_state.py
uv run pytest -q tests/storage/test_index_store.py tests/test_service.py tests/test_mcp_server.py
uv run pytest -q tests/graph/test_anchor_benchmark.py tests/graph/test_traversal_benchmark.py
uv run pytest -q
~~~

Static repository hygiene:

~~~sh
git diff --check
git status --short
shasum -a 256 /Users/brummerv/llm-wiki/tests/fixtures/graph_shape_traversal_stage3.json
rg -n "subprocess|os\.system|Popen|socket|urllib|requests|httpx" src/loci/graph/javascript_modules.py
~~~

The subprocess/network scan is reviewed, not blindly treated as proof. The new
module should contain none of those execution/network paths.

## Frozen Benchmark Rule

The frozen fixture is read-only and must retain SHA-256:

~~~text
c52def1bdf592ad735149d199910f74183598eccd9ccf8064335fa0cd0e84e27
~~~

Stage 8 does not change anchor selection, traversal, ranking, Markdown graph
inputs, or llm-wiki integration. Therefore:

- always verify the checksum before and after implementation;
- always run the local anchor/traversal benchmark unit tests;
- do not edit the fixture or production-tune against its expected answers;
- do not run judges or model scorers; and
- run the expensive end-to-end frozen replay only if the llm-wiki graph digest,
  traversal output, or relevant generic retrieval tests drift.

If such drift appears, stop before acceptance and explain it. Do not normalize
the benchmark or broaden this stage to hide the regression.

## Real-repository Review

The final packet must include a clean-room reindex of
`/Users/brummerv/phluxxed/anvil_redux`, which currently provides a real modern
Node/TypeScript case:

- `package.json` has `type: "module"`;
- `tsconfig.json` has `module: "nodenext"`, `noEmit`, and explicit source
  inclusion;
- local imports use explicit `.ts` paths; and
- Node built-ins and installed MCP/Zod dependencies must remain external, not
  fabricated repository edges.

Acceptance evidence records:

1. resolved local import count and representative exact targets;
2. external builtin/package observations with no edges;
3. `resolution_basis` and control files for representative records;
4. no source, manifest, config, lockfile, or generated-output modification;
5. identical results after a fresh process and an incremental no-op reindex;
   and
6. bounded index time and graph-size delta compared with the pre-stage Loci
   index.

The controlled test matrix supplies npm/pnpm workspace coverage that Anvil does
not currently contain. A second real workspace repository may be added to the
review packet if one is available and authorized, but its absence does not
weaken the deterministic fixture gate or authorize network cloning.

## Owner Review Gate

Before implementation, the owner reviews this plan at product level. Approval
means agreement that:

- Loci should understand the explicit repository controls developers use to
  say where an import goes;
- it should keep exact file-level targets and leave generated-only entries
  unresolved rather than inventing source mappings;
- it should not execute toolchains, inspect installs, use the network, or add
  judges;
- static import/export coverage is the Stage 8 boundary;
- unsupported loader-specific behavior remains visible rather than guessed;
  and
- Cargo-aware Rust remains the next roadmap item after Stage 8 acceptance.

After implementation, Stage 8 is accepted only when the final review packet
shows all of the following:

- [ ] every focused gate and the full suite pass;
- [ ] exact API and persistence contracts match this plan;
- [ ] adversarial containment and bound tests pass;
- [ ] full/incremental/fresh-process outputs agree;
- [ ] existing Python, Go, Rust, Markdown, and retrieval behavior is preserved;
- [ ] Anvil real-repository evidence is correct and source remains untouched;
- [ ] frozen benchmark checksum and local benchmark tests pass;
- [ ] no judge/model call occurred;
- [ ] documentation states supported and unsupported semantics without claiming
      universal runtime parity;
- [ ] final diff, secret scan, and remote readback are clean; and
- [ ] the owner explicitly accepts the final review packet.

Only then may the governing design status change from Stages 1-7 accepted to
Stages 1-8 accepted and the roadmap advance to Cargo-aware Rust.

## Rollback

Rollback is code/index-only:

1. revert the Stage 8 implementation and documentation commits;
2. restore extractor version 6 and graph-state schema 3 code;
3. rebuild affected indexes under the restored code; and
4. verify JavaScript/TypeScript returns to the Stage 6 relative `.ts`/`.tsx`/`.js`
   subset, with package/config imports external and no control provenance.

No repository source, manifest, config, workspace file, benchmark fixture, or
llm-wiki data is migrated by Stage 8, so none requires content rollback.

During implementation, failure must not leave a valid-looking partial graph:

- invalid persisted schema forces rebuild or a structured error;
- invalid controls exclude the affected context and persist a warning;
- unresolved imports persist and produce no edge;
- record/edge validation failure aborts the atomic index write; and
- no fallback guesses by filename, directory, package name, or symbol are
  permitted.

## Risks and Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Loci claims a package edge that depends on an ambient install | High | Active workspace + owner dependency + exact contained entry; never inspect node_modules |
| Missing dist output is guessed back to source | High | Only official one-to-one local self/import remap; cross-workspace missing output stays unresolved |
| Node ESM and bundler lookup rules are mixed | High | Effective request mode; unknown modes must converge or remain ambiguous |
| A tsconfig alias is treated as runtime proof | Medium | Distinct `compiler_paths`/`compiler_base_url` basis and documented compiler-evidence meaning |
| An unrelated config captures a source file | High | Deepest owning standard config plus files/include/exclude membership |
| Conditional exports silently choose one environment | High | Ordered effective conditions; unknown import/require context must converge |
| Workspace glob expansion is unbounded or manager-specific | High | Small common glob subset over discovered manifests only; unsupported forms fail closed |
| Control edit fails to refresh unchanged imports | High | Every read/rejected control hash joins graph input hashes; add/change/delete tests |
| Invalid control creates a refresh loop | Medium | Stable sentinel hash plus persisted diagnostic |
| New extensions disappear from existing indexes | High | Extractor version 7 forces full rebuild |
| Strict import fields misload old state | High | Graph-state schema 4, no fabricated compatibility fields |
| The subsystem becomes an unmaintainable resolver clone | Medium | Bounded module with frozen semantics; no tool execution; later expansion requires evidence and review |
| Stage 8 perturbs wiki traversal | Low | No traversal/Markdown code changes; checksum and local benchmark gates |

## Evolution Rule

This plan is a strong current contract, not a permanent declaration that these
are the only useful JavaScript/TypeScript semantics.

After Stage 8 acceptance, a deferred feature can move into the trusted subset
when a real Anvil/project need, official ecosystem change, or measured false
negative justifies it. The change must identify its evidence, deterministic
boundary, compatibility effect, tests, and review gate. Until then, Loci stays
honest by returning unresolved.

## Open Questions

None block implementation after owner approval.

The deliberately unsupported areas most likely to earn a later design are
literal dynamic imports, unshadowed CommonJS `require`, package-map arrays,
lockfile-proven workspace aliases, custom build configs selected by scripts,
and framework/bundler aliases. They must not be patched into Stage 8 ad hoc.
