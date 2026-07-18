# Final Review: Extensible Graph Retrieval Stage 8 — JavaScript/TypeScript Import Resolution

- **Status:** accepted by owner on 2026-07-18
- **Date:** 2026-07-18
- **Repository:** `/Users/brummerv/loci`
- **Governing plan:** `docs/plans/2026-07-18-extensible-graph-retrieval-stage-8-javascript-typescript-import-resolution.md`
- **Baseline:** `6f4f3d63c8c143787b242dadc41bc8d6550ba46d` (590 tests)
- **Reviewed implementation head:** `788069103e1d07adbb78a2732b1b0cb74a3a2b30`
- **Frozen benchmark:** `/Users/brummerv/llm-wiki/tests/fixtures/graph_shape_traversal_stage3.json`

## Owner-level outcome

Loci can now follow static JavaScript and TypeScript imports through the
repository controls that developers use to describe their project. That
includes relative files, the full JS/TS extension family, standard TypeScript
and JavaScript project configuration, declared npm-style and pnpm workspaces,
package exports/imports, self-references, and conservative legacy entries.

The result is still an exact, directed edge to one indexed file. Every JS/TS
diagnostic record says which resolution rule won and which repository controls
justified it. If the evidence is missing, ambiguous, inaccessible, malformed,
or outside the supported static contract, Loci keeps an unresolved record and
does not invent an edge.

This stage does not run Node, TypeScript, a package manager, a bundler, a
generator, a script, or repository code. It does not inspect installed
`node_modules`, package-manager stores, lockfile-selected installations, or the
network. Dynamic `import()`, shadowable `require()`, custom loaders, bundler
aliases, and missing generated output remain outside the trusted contract.

## Delivered contract

The implementation provides the approved public-to-Loci APIs:

- `load_javascript_module_context(repo_path, control_candidates)` performs all
  bounded repository I/O and returns controls, hashes, and bounded problems;
- `build_javascript_resolution_index(context, file_nodes=...)` constructs
  frozen lookups without repository I/O;
- `resolve_javascript_import(raw, index)` is a pure, candidate-bounded resolver;
- `resolve_import`, `resolve_imports`, and `materialize_graph` accept the
  JavaScript index additively;
- `graph_imports` and `loci_graph_imports` retain their exact input contract and
  add `resolution_basis` plus `resolution_control_files` to each item; and
- graph edges retain the accepted `loci:imports|imports_type`, directed,
  `import-resolved`, exact-evidence shape.

Persistence is intentionally incompatible with stale strict records:

- graph-state schema is 4;
- extractor version is 7;
- index schema remains 5; and
- public graph schema remains 1 because the response change is additive.

Python, Go, and Rust records carry null/empty JavaScript provenance. Existing
Python file targets and Go package targets retain their semantics. Rust remains
extract-and-report only with no trusted import edge.

## Implementation slices

The approved work landed as reviewable commits:

| Commit | Purpose |
| --- | --- |
| `79e1f0c` | approve and freeze the detailed Stage 8 plan |
| `a0f1092` | add bounded package/workspace/project control loading |
| `ccdb9e8` | index and extract all eight JS/TS source extensions |
| `0ab4d28` | add deterministic repository-local resolution |
| `2b9b8b6` | persist resolution basis and control provenance |
| `4b9943f` | materialize configured imports as exact graph edges |
| `467c968` | connect service scanning, freshness, and diagnostics |
| `9206cdd` | prove fresh-process MCP output and document the contract |
| `3f226cf` | remove the superseded relative-only resolver |
| `7880691` | resolve adversarial review findings and split review boundaries |

The review-driven internal split is the only file-topology deviation from the
plan. `javascript_modules.py` remains the stable public facade and bounded
control loader; `_javascript_resolution.py` owns the pure builder/resolver.
This reduced one 1,975-line mixed-responsibility file to two independently
reviewable modules (1,094 and 991 lines at the reviewed head) without changing
the approved API, persistence, service, MCP, or trust boundary.

## Five-axis code review

### Correctness

The implementation matches the frozen resolution order, exact-file target
contract, provenance invariants, service freshness flow, schema upgrades, and
unchanged MCP inputs. Full, incremental, and fresh-process tests agree.

The final adversarial pass found and fixed five defects before publication:

1. pnpm exclusion patterns could remove the workspace root even though pnpm
   always includes it;
2. an explicit TypeScript path was tried before declared `moduleSuffixes`;
3. `node10`/`classic` mode used modern package maps by default instead of the
   legacy entry path;
4. string sugar was incorrectly admitted for private package `imports`; and
5. deeply nested YAML was shape-rejected only after parsing instead of being
   rejected at the frozen nesting bound.

Regression tests now prove each correction. Additional review tests cover
post-`lstat` growth, longest compiler-path precedence and fallback, package-map
patterns/null blocks/encapsulation, and per-observation candidate exhaustion.

### Readability and architecture

The repository-I/O boundary and pure resolution boundary are separate. The
old relative-only implementation and its unused helpers were removed rather
than retained as a compatibility fork. The public facade preserves one stable
import surface for service, materialization, and tests.

### Security

Controls are treated as untrusted input. Reads require lexical and real-path
containment, regular non-symlink identity, byte ceilings, strict UTF-8, bounded
JSON/JSONC/YAML depth, duplicate-key rejection for JSON, safe restricted YAML,
bounded counts, and bounded diagnostics that do not echo control values or
absolute host paths.

A static scan found no subprocess, shell, socket, HTTP-client, or network path
in either JavaScript module. The reviewed change contains no detected common
private-key or provider-token signature. No dependency was added.

### Performance

Control, config, workspace, package-map, and per-observation candidate limits
are enforced. Resolution operates on frozen maps and indexed-file sets rather
than performing filesystem traversal per import. Public import inspection
retains its 500-record pagination ceiling.

On the real Anvil repository a clean full index completed in 8.326 seconds. An
incremental no-op index completed in 8.114 seconds, reused all 352 indexable
files, and produced byte-equivalent graph content. Loci itself clean-indexed in
1.611 seconds.

## Verification evidence

All required focused gates passed at the reviewed head:

| Gate | Result |
| --- | --- |
| JavaScript module loader/resolver | 46 passed |
| parser import/extractor compatibility | 58 passed |
| import/materialization/state contracts | 108 passed |
| storage/service/fresh-process MCP | 160 passed |
| local anchor/traversal benchmarks | 15 passed |
| complete repository suite | 665 passed in 37.48 seconds |
| package build | sdist and wheel built successfully |
| `git diff --check` | clean |

The test total increased from 590 to 665. No judge, model scorer, or wiki audit
was run. The frozen end-to-end replay was not needed because the generic local
benchmark gates passed and the frozen fixture checksum did not drift.

Frozen fixture SHA-256 before and after implementation:

```text
c52def1bdf592ad735149d199910f74183598eccd9ccf8064335fa0cd0e84e27
```

The pre-stage live Loci index recorded 720 graph edges and 347 import
observations (160 resolved, 187 unresolved). The clean reviewed index records
786 edges and 416 observations (195 resolved, 221 unresolved). The increase is
explained by the new implementation modules and documentation; graph health is
healthy with no diagnostics.

## Real-repository acceptance: Anvil

The clean-room target was `/Users/brummerv/phluxxed/anvil_redux` at commit
`948e53722911ec432af026daf0f9895367073258`.

Before and after indexing:

- `git status --short` was empty;
- the aggregate SHA-256 over tracked working files was unchanged at
  `a73b12f6bd8be476dc957e0e2794c06ec16a98a1c116a2181a906e6d6db18a79`;
- `package.json` remained
  `9f951e4cac6875cc57b14f4efca315f38ebc0420b299432fb14da33ec4ee30ea`;
- `package-lock.json` remained
  `34e09b810e5f23c15fe081292398abebcc2447cbf65e3ca93ab72bb50e99f2b3`;
  and
- `tsconfig.json` remained
  `901c0a2e2ce1cd0c3cbec586b806fb8b761242e8f37ee13830774a821c99c8d1`.

The clean index was healthy with:

- 92 code file nodes;
- 7,563 total graph edges;
- 665 import observations;
- 456 resolved and 209 unresolved observations; and
- no graph diagnostics.

For JavaScript/TypeScript specifically, 206 observations resolved through the
`relative_path` basis and 128 remained external. Representative exact records
include:

```text
bin/anvil.ts
  ../src/continuity/index.ts
  -> src/continuity/index.ts
  basis: relative_path
  controls: package.json, tsconfig.json

bin/anvil.ts
  ../src/brain-usage/recall.ts
  -> src/brain-usage/recall.ts
  basis: relative_path
  controls: package.json, tsconfig.json
```

`bin/anvil.ts` exposes 14 unique outgoing import edges. Runtime and type-only
imports remain distinct, all point forward to exact file nodes, and all retain
the importing source line and content hash as evidence.

Installed packages and built-ins remained non-edges, for example:

```text
@modelcontextprotocol/sdk/client/index.js -> unresolved/external
@modelcontextprotocol/sdk/client/stdio.js -> unresolved/external
node:child_process                       -> unresolved/external
node:fs/promises                         -> unresolved/external
node:http                                -> unresolved/external
```

The fresh-process read returned the same persisted records. A no-op incremental
reindex produced identical graph digest
`5cd0f4e37a641571cafff2375b347ca37505780ec32332d1f5d9c5cd7f2ec2a3`
before and after.

## Compatibility and limitations

- The MCP tool list and `loci_graph_imports` input schema are unchanged.
- Existing counts, sorting, filtering, status, pagination, target fields, and
  graph schema remain unchanged.
- Old graph-state/extractor versions force a full rebuild; no compatibility
  shim fabricates provenance.
- Normal unresolved outcomes do not degrade graph health. Invalid controls do
  degrade health while source navigation remains available and refresh remains
  stable.
- Package-map arrays, versioned `types@...` conditions, package-based config
  inheritance, custom configs not reached by local `extends`, installed-package
  resolution, lockfile interpretation, custom loaders, and dynamic observations
  remain deliberately unsupported.
- Cargo-aware Rust resolution remains the next dependency-layer roadmap item.

## Final owner gate

- [x] every focused gate and the full suite pass
- [x] exact API and persistence contracts match the approved boundary
- [x] adversarial containment, depth, count, and candidate-bound tests pass
- [x] full, incremental, and fresh-process outputs agree
- [x] Python, Go, Rust, Markdown, and generic retrieval behavior is preserved
- [x] Anvil evidence is correct and its source repository remained untouched
- [x] frozen benchmark checksum and local benchmark tests pass
- [x] no judge or model call occurred
- [x] user and agent documentation state supported and unsupported semantics
- [x] final code review, build, diff hygiene, and secret/execution scans are clean
- [x] implementation and this review packet were committed and pushed directly;
      remote `master` was read back after publication
- [x] owner explicitly accepts this final review packet

The owner explicitly accepted this packet on 2026-07-18. The governing design
now records Stages 1-8 as accepted. The next roadmap item is the separately
scoped Cargo-aware Rust dependency-resolution design gate.
