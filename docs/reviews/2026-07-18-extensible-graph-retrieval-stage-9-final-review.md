# Final Review: Extensible Graph Retrieval Stage 9 — Cargo-aware Rust Dependency Resolution

- **Status:** implementation and final evidence complete; explicit owner acceptance pending
- **Date:** 2026-07-20
- **Repository:** `/Users/brummerv/loci`
- **Governing plan:** `docs/plans/2026-07-18-extensible-graph-retrieval-stage-9-cargo-aware-rust-dependency-resolution.md`
- **Baseline:** `2a3b33505ba388e652e257c686edadbc524df4e6` (665 tests)
- **Reviewed implementation head:** `20cdaa2e3afa3ceae93cbedf7848b3f775e906da`
- **Reviewed commit range:** `2a3b33505ba388e652e257c686edadbc524df4e6..20cdaa2e3afa3ceae93cbedf7848b3f775e906da`
- **Frozen benchmark:** `/Users/brummerv/llm-wiki/tests/fixtures/graph_shape_traversal_stage3.json`

## Owner-level outcome

Loci can now follow repository-contained Rust dependencies using the same static
evidence a human would inspect in Cargo manifests and Rust module declarations.
It understands packages, workspaces, library and binary targets, local path
dependencies, renamed dependencies, module files, inline modules, editions,
visibility, aliases, re-exports, and configuration-dependent declarations.

In plain terms, Loci can prove that a Rust file depends on another exact Rust
file or on one exact Cargo crate target. It records why that answer is valid and
which manifest files support it. If the answer is private, external, missing,
ambiguous, configuration-uncertain, or otherwise not provable from the bounded
static evidence, Loci records the honest failure and creates no trusted edge.

This remains static analysis. Indexing does not run Cargo, rustc, Git,
repository code, build scripts, macros, a package manager, or the network. A
relationship labeled `declared_possible` means the repository declares a
configuration in which it can exist; it is not a claim about the active build.

## Delivered contract

The implemented internal APIs are:

- `load_cargo_context(repo_path, control_candidates)` reads bounded, contained
  Cargo controls and returns immutable package/workspace/target context,
  control hashes, and bounded problems;
- `build_rust_crate_index(context, file_nodes=..., observations=...)` builds
  validated crate nodes, module ownership, and dependency bindings without
  repository I/O;
- `resolve_rust_import(raw, crate_index, resolver_index)` resolves one Rust
  observation through Cargo, edition, module, alias, visibility, and
  configuration evidence;
- `resolve_import`, `resolve_imports`, and `materialize_graph` accept the Rust
  indexes additively; and
- `graph_imports` and `loci_graph_imports` keep their existing input schema and
  expose strict Rust context, file/crate target shape, Cargo resolution basis,
  control files, and configuration class.

Resolved edges retain the accepted directed `loci:imports|imports_type` and
`import-resolved` shape with exact source-line/hash evidence. Crate endpoints
are validated synthetic `kind="crate"` nodes tied to one manifest, target, and
indexed crate root.

Persistence versions at the reviewed head are:

- public graph schema: 1;
- outer index schema: 5;
- extractor version: 9; and
- private graph-state schema: 6.

Graph-state schema 6 adds only `rust_module_observations`, a strictly validated
private list of inline Rust module declarations. These observations preserve
module ownership across an unchanged incremental index. They never appear in
`loci_graph_imports` and never create an edge. Older graph states fail the
strict version check and rebuild; there is no compatibility shim.

## Review-discovered persistence correction

The first final-review harness found a real defect before acceptance. A clean
full index resolved:

~~~text
use single_app::inline::nested::InlineThing
    -> src/lib.rs::__file__#file
~~~

An unchanged incremental index instead fell back to the enclosing crate node.
The source files were correctly skipped, but the prior persisted state retained
only public import records. Inline module declarations are intentionally not
public imports, so the module ownership facts needed for re-resolution had been
discarded.

Commit `20cdaa2` fixes the issue by persisting only those hidden structural
observations in graph-state schema 6 and restoring them for skipped files. A
regression test also replaces import extraction with a deliberate failure
during the no-op incremental run, proving the fix does not reparse unchanged
Rust source. The corrected production MCP harness now reports:

~~~text
target_kind: file
target_file: src/lib.rs
target_id:   src/lib.rs::__file__#file
full/incremental serialized SHA-256 equal: true
persisted structural observations: 2
public inline-module import records: 0
~~~

## Implementation commits

| Commit | Purpose |
| --- | --- |
| `1ca254b` | approve and freeze the detailed Stage 9 plan |
| `b402a3d` | add bounded Cargo context loading |
| `d859d9c` | expand deterministic Rust use-tree observations |
| `c14e6d8` | extract strict Rust dependency context |
| `72b6f29` | expand parser grammar coverage |
| `df11c69` | align persistence tests with extractor version 9 |
| `90f8193` | record Task 2 completion |
| `97a75b1` | preserve inline-module lexical context |
| `0358b9b` | model inline modules without false import edges |
| `e95fd15` | build Cargo target, crate, and module ownership indexes |
| `571bce6` | record Task 3 completion |
| `0a2de68` | resolve Rust imports from Cargo/module context |
| `6b8a24a` | preserve bounded ambiguity outcomes |
| `adb50be` | materialize validated Rust file/crate edges |
| `abdf33a` | activate Cargo-aware service indexing and freshness |
| `199733b` | prove the fresh-process production MCP contract |
| `20cdaa2` | preserve inline-module ownership incrementally |

Exact files changed in the reviewed range:

~~~text
README.md
docs/design/2026-07-13-extensible-graph-retrieval-design.md
docs/plans/2026-07-18-extensible-graph-retrieval-stage-9-cargo-aware-rust-dependency-resolution.md
pyproject.toml
skills/loci/SKILL.md
src/loci/graph/_cargo_targets.py
src/loci/graph/_cargo_workspace.py
src/loci/graph/_rust_aliases.py
src/loci/graph/_rust_import_schema.py
src/loci/graph/_rust_resolution.py
src/loci/graph/_rust_semantics.py
src/loci/graph/contracts.py
src/loci/graph/imports.py
src/loci/graph/materialize.py
src/loci/graph/retrieval.py
src/loci/graph/rust_crates.py
src/loci/graph/state.py
src/loci/parser/imports.py
src/loci/parser/languages.py
src/loci/service.py
src/loci/storage/index_store.py
tests/graph/test_contracts.py
tests/graph/test_imports.py
tests/graph/test_materialize.py
tests/graph/test_rust_crates.py
tests/graph/test_state.py
tests/parser/test_imports.py
tests/parser/test_languages.py
tests/storage/test_index_store.py
tests/test_mcp_server.py
tests/test_service.py
uv.lock
~~~

This review packet and the final pending-acceptance status edits in the
governing plan/design are publication-only changes after the reviewed code
head; they do not widen the implementation range or runtime behavior.

## Five-axis code review

Review result: the one blocking persistence defect found by the final harness
was fixed in `20cdaa2`. No unresolved blocking, high, or medium finding remains.

### Correctness

The implementation follows the frozen Cargo ownership, Rust edition/path,
module declaration, alias convergence, visibility, and declared-possible
contracts. It never falls back to repository-wide filename, crate-name,
package-name, or symbol-name matching. Resolution stops at the deepest definite
file or crate endpoint; terminal item ownership remains a later stage.

The final pass specifically re-proved full/incremental byte equality, skipped
source reuse, fresh-process equality, exact inline-module ownership, self-edge
suppression, current validated crate endpoints, and all stable unresolved
reasons.

### Readability and architecture

Bounded repository I/O lives in the Cargo loader. Target construction,
workspace normalization, alias convergence, Rust semantics, and final
resolution are split into focused modules. Service orchestration passes frozen
indexes into the pure resolver rather than mixing filesystem traversal into
per-import resolution.

The graph-state correction is deliberately narrow: it reuses the existing
strict raw-observation serializer, stores only inline Rust module declarations,
and leaves public import inspection untouched.

### Security

Cargo controls are untrusted input. Tests cover lexical and real-path
containment, symlink and non-regular rejection, byte/depth/count ceilings,
strict UTF-8, duplicate/invalid TOML, post-check growth, workspace/path escape,
missing or ambiguous ownership, and redacted diagnostics. Count ceilings reject
the whole affected context instead of truncating it into misleading partial
truth.

A production `loci-mcp` harness placed failing `cargo`, `rustc`, `git`, and
`curl` shims before the runtime path, replaced Python subprocess and socket
entry points with failing guards, and indexed all three repositories. No guard
marker was created. A static scan found no subprocess, shell, socket, or HTTP
client import/call in the Stage 9 production modules.

### Performance

Repository discovery still performs one bounded root scan. Cargo controls and
source files are collected from that scan; resolver construction uses frozen
maps and bounded candidate sets. A no-op incremental index reuses unchanged
source observations, including the newly persisted inline-module metadata,
without reparsing Rust source.

### Compatibility

The MCP tool list remains 17 tools. `loci_graph_imports` keeps the same five
inputs: `repo`, `file`, `status`, `offset`, and `limit`. Python,
JavaScript/TypeScript, and Go targets retain their existing file/package
semantics; Markdown profiles, contributions, anchors, traversal, paths,
retrieval, search, outline, exact reads, grep, health, and verification pass the
complete suite.

## Verification evidence

The exact final matrix passed at `20cdaa2`:

| Gate | Result |
| --- | --- |
| `uv lock --check` | resolved 47 packages; lock current |
| Cargo loader/crate index | 33 passed |
| parser import extraction | 24 passed |
| import/materialization/contract/state | 239 passed |
| storage/service/fresh-process MCP | 169 passed |
| local anchor/traversal benchmarks | 15 passed |
| complete repository suite | 808 passed in 42.46 seconds |
| Python compileall | passed |
| package build | sdist and wheel built successfully |
| `git diff --check` | clean |

No judge, model scorer, or paid evaluation ran. The frozen deterministic local
benchmark tests ran as part of the suite.

Frozen fixture SHA-256:

~~~text
c52def1bdf592ad735149d199910f74183598eccd9ccf8064335fa0cd0e84e27
~~~

The checksum matches the frozen value and the llm-wiki worktree reports no
change to the fixture.

## Production MCP acceptance repositories

The production command was `loci-mcp`. The disposable roots lived under
`/tmp/loci-stage9-review-20260720`; they are evidence fixtures only and are not
part of the repository.

| Fixture | Crates | Imports | Resolved/unresolved | Health | Verify |
| --- | ---: | ---: | ---: | --- | --- |
| single package, lib/bin, inline/external modules | 2 | 6 | 4 / 2 | healthy | 11 / 11 |
| virtual workspace with renamed/inherited/target-specific paths | 2 | 5 | 4 / 1 | healthy | 10 / 10 |
| adversarial controls/modules/same-name traps | 2 | 9 | 3 / 6 | degraded as designed | 12 / 12 |

Representative trusted graph results:

- `single_app::api::Thing` reaches `src/api.rs` as an unconditional file edge;
- `single_app::inline::nested::InlineThing` reaches `src/lib.rs` as an
  unconditional file edge;
- `core_alias::public_api::Thing` reaches
  `crates/core/src/public_api.rs` through inherited workspace dependency
  evidence and is labeled `declared_possible`;
- `target_core::RootThing` reaches the crate node
  `crates/core/Cargo.toml::lib:core_lib#crate` through a target-specific path
  dependency and is labeled `declared_possible`; and
- `loci_get` returned the exact selected symbol
  `crates/core/src/public_api.rs::Thing#struct` with source
  `pub struct Thing;`.

`loci_graph_traverse_neighbors`, `loci_graph_paths`, and
`loci_graph_retrieve` reached both file and crate endpoints. The retrieved
workspace path was supported by a direct authored import edge.

Required outcome coverage:

| Outcome | Evidence |
| --- | --- |
| unconditional | `single_app::api::Thing` -> `src/api.rs`, `cargo_package_library` |
| declared possible/file | `core_alias::public_api::Thing` -> `crates/core/src/public_api.rs`, `cargo_workspace_dependency` |
| declared possible/crate | `target_core::RootThing` -> `crates/core/Cargo.toml::lib:core_lib#crate`, `cargo_path_dependency` |
| inaccessible | `core_alias::private_api::Secret` -> `unresolved/inaccessible` |
| ambiguous | duplicate module source -> `unresolved/ambiguous` |
| external | same-named repository `serde` trap -> `unresolved/external` |
| not indexed | missing module source -> `unresolved/not_indexed` |
| unsupported | uncertain cfg/path route -> `unresolved/unsupported_configuration` |

The adversarial health payload reported only stable reasons:
`invalid_toml`, `path_outside_repository`,
`unsupported_module_configuration`, `ambiguous_module_source`,
`cyclic_module_source`, and `module_source_not_indexed`. It exposed neither the
fixture secret nor an absolute host path in diagnostics. No resolved self-edge
was returned.

## Persistence and restart evidence

A second fresh MCP server process read every stored repository without
rebuilding. Import, health, traversal, path, retrieval, exact-get, and verify
responses were equal, and index SHA-256 plus modification time were unchanged.

The subsequent no-op incremental index skipped all Rust source files and
produced byte-identical serialized indexes:

| Fixture | Full/incremental SHA-256 |
| --- | --- |
| single | `87dba4aed30735c8dc64f355c4601119f702375c11e79753d46055156822f8fe` |
| workspace | `a95ccb7d7e34a149eeedeac2da6a1c99e840465cc6616b3574e7df0b3b782234` |
| adversarial | `f675d4e14c988a0a877a1213282f7128d41b48f89d3a58d3c6a264be9e2cde62` |

## Residual limitations and next boundary

- Registry and Git dependencies remain external even when a same-named package
  exists in the repository.
- Features, target predicates, required features, and supported cfg produce
  declared-possible static edges; Loci does not know the active Cargo build.
- Macro-generated modules/items, build-script output, generated files, custom
  toolchain behavior, and unsupported cfg/path expressions remain unresolved.
- Glob routes, cyclic aliases, divergent conditional aliases, ambiguous module
  sources, inaccessible modules, and paths outside the indexed repository do
  not become trusted edges.
- Stage 9 proves the deepest definite module file or owning crate. Resolving the
  terminal symbol is the next roadmap stage; cross-file calls follow only after
  definite symbol binding exists.

No later-stage symbol ownership, call graph, heuristic edge, or architecture
analysis entered this implementation.

## Final review questions

- Every trusted Rust edge has exact Cargo/module evidence: **yes**.
- Repository-wide name/filename fallback can create an edge: **no**.
- Every crate endpoint identifies one validated target and indexed root:
  **yes**.
- Conditional relationships are distinct from active-build truth: **yes**.
- Supported module privacy and dependency-kind boundaries are enforced:
  **yes**.
- Malformed controls and combinatorial inputs are bounded and diagnostics are
  redacted: **yes**.
- Later-stage symbol/call resolution entered the implementation: **no**.

## Final owner gate

- [x] exact implementation and changed-file range recorded
- [x] focused tests, complete suite, compile, build, and diff hygiene pass
- [x] frozen checksum matches and the fixture is unmodified
- [x] production MCP proves exact Rust file and crate endpoints
- [x] every required resolved/unresolved outcome is represented
- [x] execution and network guards remain untouched during indexing
- [x] path, symlink, bounds, ambiguity, and diagnostic-redaction evidence passes
- [x] full, incremental, and fresh-process results agree
- [x] Python, JavaScript/TypeScript, Go, Markdown, and generic graph behavior pass
- [x] residual limitations and the next-stage boundary are explicit
- [x] implementation and review packet are committed and pushed directly to `master`
- [ ] owner explicitly accepts this final review packet

Stage 9 is implemented and ready for acceptance, but it is not marked accepted
until the owner explicitly approves this packet.
