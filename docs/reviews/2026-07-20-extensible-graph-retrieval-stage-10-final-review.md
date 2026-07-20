# Final Review: Extensible Graph Retrieval Stage 10 — Resolved Symbol References

- **Status:** implementation accepted by engineering review; awaiting explicit owner acceptance
- **Date:** 2026-07-20
- **Repository:** `/Users/brummerv/loci`
- **Governing plan:** `docs/plans/2026-07-20-extensible-graph-retrieval-stage-10-resolved-symbol-references.md`
- **Accepted predecessor:** `11f21f8` (Stage 9 accepted)
- **Reviewed implementation head:** `366ca00`
- **Reviewed commit range:** `11f21f8..366ca00`
- **Frozen benchmark:** `/Users/brummerv/llm-wiki/tests/fixtures/graph_shape_traversal_stage3.json`
- **Frozen SHA-256:** `c52def1bdf592ad735149d199910f74183598eccd9ccf8064335fa0cd0e84e27`

## Owner-level outcome

Loci can now prove a narrower and more useful relationship than “this file
imports that file.” When source code uses an imported class, function, type,
constant, interface, struct, or other supported indexed definition, Loci can
connect the unique containing source symbol to the exact imported target.

In plain terms, an agent can ask “what imported symbols does this function
name?”, “who names this class?”, or “show me the source line supporting this
path?” Loci can answer through its normal graph tools and retrieve the final
target source. If the import, binding, export, visibility, configuration, or
source ownership is not definite, Loci keeps an inspectable unresolved record
and creates no trusted relationship.

This is not a call graph. A reference proves that source names a target; it does
not prove invocation, overload selection, trait dispatch, runtime activation,
or behavior. Cross-file calls remain the separately reviewed Stage 11 boundary.

## Delivered contract

The implemented path is:

```text
tree-sitter syntax
  -> strict import bindings, local exports, lexical uses, and shadowing evidence
  -> one already-resolved import endpoint
  -> one supported endpoint export surface
  -> one exact accessible indexed target symbol
  -> validated SymbolReferenceRecord
  -> directed loci:references|references_type / import-resolved edge
```

The source is the unique smallest indexed owner of the use; module-level uses
belong to the source file node. Repeated uses retain diagnostic records, while
the trusted graph deduplicates identical source/type/target relationships using
the earliest deterministic evidence.

Runtime uses materialize `type="references"`. Explicitly type-only TypeScript
uses materialize `type="references_type"`. Both are directed,
`namespace="loci"`, `resolution="import-resolved"`, and carry the exact source
line and source hash.

The public diagnostic API is:

```python
graph_references(
    repo,
    *,
    file=None,
    status="all",       # all | resolved | unresolved
    offset=0,
    limit=100,          # 1..500
    ensure_fresh=False,
)
```

The MCP surface adds exactly one tool with the same five user inputs:

```text
loci_graph_references(repo, file=None, status="all", offset=0, limit=100)
```

It delegates with `ensure_fresh=True` through the existing structured
`LociError` adapter. File filtering precedes counts, status filtering precedes
pagination, and records sort stably by source position, binding identity, and
target identity. Existing generic traversal and path APIs consume the standard
edges. `loci_graph_neighbors` remains contains-only, and no CLI command exists.

Persistence versions at the reviewed head are:

- public graph schema: 1;
- outer index schema: 5;
- extractor version: 10; and
- private graph-state schema: 7.

Schema 7 persists strict export and symbol-reference observations inside
`index.json.graph`. Older private state or extractor versions fail the existing
version check and rebuild completely; no compatibility shim or migration layer
was added.

## Supported language boundary

### Python

Direct imported symbols, aliases, imported modules plus members, unaliased
dotted modules, and bounded explicit re-export chains are supported. Parameters,
assignments, nested imports, and other lexical bindings suppress shadowed uses.
Star imports, dynamic exports, ambiguous cycles, inaccessible/missing targets,
and wrong-directory same-name decoys create no edge.

### JavaScript and TypeScript

Default, named, aliased, namespace, statement/per-specifier type-only imports,
local exports, named re-exports, and bounded star-barrel chains are supported
across `.ts`, `.tsx`, `.mts`, `.cts`, `.js`, `.jsx`, `.mjs`, and `.cjs`.
Workspace/package/project controls retain Stage 8 provenance. Star conflicts,
anonymous defaults without an indexed target, computed member access,
shadowable CommonJS `require`, unsupported controls, externals, and decoy
packages fail closed.

### Go

Qualified identifiers can resolve through same-module packages, active
workspaces, and contained local replacements. Declared package names, aliases,
Unicode-exported names, package visibility, command/inaccessible packages, and
ambiguous duplicate alternatives are enforced. Dot/blank imports, local
shadowing, unexported items, external modules, and repository-wide package-name
or filename guesses create no edge.

### Rust

The bounded subset follows Stage 9 crate/module ownership through same-crate
modules, same-package libraries, contained path dependencies, aliases, named
re-exports, item/module visibility, editions, and convergent declared-possible
configuration. Private or inaccessible items, globs/preludes without one exact
target, macros/generated code, associated-item or trait ambiguity, external
crates, divergent configuration, and same-name decoys create no edge.

Official semantics and installed grammar evidence remain recorded in the
governing plan:

- Python import, import-statement, and execution-model references;
- TypeScript module/import/export reference;
- Go language specification;
- Rust use, path, visibility, conditional-compilation, and namespace references;
- `tree-sitter-language-pack` declared `>=0.7.0`, locked/installed `0.13.0`;
- MCP declared `>=1.27,<2`, locked/installed `1.28.0`.

## Implementation commits

| Commit | Purpose |
| --- | --- |
| `f1b2898` | approve and freeze the detailed Stage 10 plan |
| `e8c9e80` | add strict parser reference models |
| `38ff20f` | extract exact import bindings |
| `857e6b7` | extract lexical symbol references |
| `2a85a39` | record the parser checkpoint |
| `b30d8b7` | add strict graph reference records |
| `b95007d` | resolve Python symbol references |
| `df46db6` | record Python resolution completion |
| `e0ec62a` | resolve direct JavaScript references |
| `f3d7eaf` | resolve named JavaScript re-exports |
| `c1e1b74` | resolve JavaScript star barrels |
| `6cd97ab` | retain unresolved JavaScript provenance |
| `76f4e86` | share JavaScript cycle detection |
| `19231e6` | record JavaScript/TypeScript completion |
| `4caf7a9` | resolve direct Go package references |
| `714fdc4` | cover Go package-reference boundaries |
| `70127ba` | simplify bounded Go reference selection |
| `fee61cd` | record Go completion |
| `fef7880` | record Rust item visibility metadata |
| `044aef5` | resolve Rust symbol references |
| `026cb7d` | validate and materialize reference edges |
| `1ba7441` | persist validated reference records |
| `5559fa3` | integrate incremental reference freshness |
| `c6587c3` | add the bounded reference diagnostic service |
| `647b66f` | expose the MCP diagnostic tool |
| `f29d947` | lock generic traversal compatibility |
| `5e70b34` | type validated MCP graph-query inputs |
| `05c5717` | record Task 10 completion |
| `366ca00` | correct the JavaScript binding type boundary found in final review |

The reviewed range changes 41 files: 14,418 insertions and 161 deletions. The
governing plan itself contributes 2,174 lines. Production work is separated
into parser models/extraction, language-specific resolvers, strict record/edge
validation, persistence/freshness, and the additive service/MCP reader; tests
account for the largest code volume.

This packet plus README, skill, plan, and design status edits are
publication-only changes after `366ca00`; they do not widen runtime behavior.

## Five-axis code review

Review result: one required type-boundary finding was fixed in `366ca00`. No
open Critical or Required correctness, security, architecture, performance, or
compatibility finding remains.

### Correctness

Tests cover exact source positions and Unicode byte ranges, strict limits and
atomic failure, syntax errors, scope/shadowing, source-owner selection,
language-specific imports/re-exports/visibility, wrong-file and cross-language
decoys, persistence, freshness, diagnostics, and edge validation. Resolved
records must match current source hashes, one current resolved import, indexed
source/target nodes, and the recorded support before materialization.

The final installed-wrapper fixtures repeated the trusted read from a fresh
process, followed the selected edge forward and backward, hydrated its exact
evidence through `loci_graph_paths`, fetched the final symbol through
`loci_get`, and proved compatibility neighbors did not widen.

### Readability and architecture

Language-specific selection lives in `_python_references.py`,
`_javascript_references.py`, `_go_references.py`, and `_rust_references.py`.
The shared resolver freezes lookup indexes before per-reference selection;
validation/materialization is separated from resolution; service/MCP code only
loads and serializes current persisted state.

`src/loci/graph/references.py` is 1,001 lines and
`src/loci/parser/references.py` is 978 lines, so both were inspected explicitly
under the repository's file-size review rule. They remain cohesive strict-model
and cross-language orchestration boundaries, while language-specific target
resolution is already split. No acceptance refactor is justified, but Stage 11
must not bolt call-specific branches into either file; new call semantics need
their own owning modules.

### Security

Repository source and control files remain untrusted input. Existing path,
real-path containment, regular-file, byte/count/depth, strict decoding,
source-hash, schema, and diagnostic-redaction boundaries apply before records
become trusted state. Bounded candidate counts, re-export pass limits, support
limits, file-reference limits, and MCP page limits prevent unbounded expansion.

Static scans found no subprocess, shell, socket, HTTP-client, or network path in
the new production modules. The disposable harness patched Python subprocess
and `os.system` routes, blocked IPv4/IPv6 socket construction and connection
helpers, and placed failing `cargo`, `rustc`, `go`, `node`, `npm`, `pnpm`,
`yarn`, `python`, `git`, and `curl` shims first on `PATH`. No tripwire fired.

No dependency changed, no frozen benchmark identifier appears in production
source, and no secret-like material is added by the Stage 10 range.

### Performance

Parsing reuses each file's existing tree. Resolution builds bounded frozen maps
and interval indexes once, then performs bounded per-reference selection. Edge
deduplication is deterministic; diagnostic reads perform one persisted-state
scan, one stable sort, and serialization of at most 500 requested records.

No-op incremental runs skipped every fixture source file and produced
byte-identical indexes. Source and control mutations re-resolved unchanged
sources without turning normal unresolved outcomes into refresh loops.

### Compatibility

The installed server advertises 18 tools, with `loci_graph_references` exactly
once and only the planned five inputs. Public graph schema 1, outer index schema
5, existing import service/MCP contracts, search, outline, exact reads, graph
health, anchors, traversal, paths, retrieval, and contains-only compatibility
neighbors remain green. No CLI or dependency was added.

## Review-discovered correction and non-gate baseline

The optional full-production Pyright diagnostic reported 36 errors before the
final correction. A detached pre-Stage-10 `11f21f8` comparison reported 39.
Blame and file comparison isolated one Stage-10-introduced error: the new
JavaScript import helper accepted `kind: str` even though `ImportBinding`
requires the closed `ImportBindingKind` literal union.

Commit `366ca00` makes that boundary exact. The targeted file now reports zero
Pyright errors and the parser matrix remains 140 passed. The current full
repository diagnostic reports 35 errors, all on older pre-Stage-10 lines and
modules; the repository did not have a clean full-Pyright gate before this
stage. This debt is recorded rather than misrepresented as a Stage 10 failure
or silently expanded into a broad cleanup.

Two earlier acceptance-harness attempts also failed before becoming evidence:

1. the first network guard replaced `socket.socket` with a function and broke
   Python SSL import; it was corrected to a real socket subclass that blocks
   only IPv4/IPv6 construction; and
2. the first JavaScript mutation check incorrectly required a resolved edge
   after removing the workspace dependency; it was corrected to require clean
   unresolved diagnostics and verification in the deliberately broken state.

Neither harness correction changed repository production behavior. The final
harness reran from a clean `/tmp` root and passed completely.

## Repository verification evidence

The final gate commands are:

```bash
.venv/bin/python -m pytest \
  tests/parser/test_imports.py \
  tests/parser/test_references.py \
  tests/parser/test_extractor.py -q

.venv/bin/python -m pytest \
  tests/graph/test_references.py \
  tests/graph/test_reference_contracts.py \
  tests/graph/test_imports.py \
  tests/graph/test_contracts.py \
  tests/graph/test_materialize.py \
  tests/graph/test_state.py -q

.venv/bin/python -m pytest \
  tests/storage/test_index_store.py \
  tests/storage/test_reference_index_store.py \
  tests/test_symbol_reference_service.py \
  tests/test_symbol_reference_mcp.py \
  tests/test_service.py \
  tests/test_mcp_server.py \
  tests/graph/test_traversal.py -q

.venv/bin/python -m pytest \
  tests/graph/test_anchor_benchmark.py \
  tests/graph/test_traversal_benchmark.py -q

.venv/bin/python -m pytest tests/ -q
uv lock --check
.venv/bin/python -m compileall -q src tests
uv build
git diff --check
shasum -a 256 \
  /Users/brummerv/llm-wiki/tests/fixtures/graph_shape_traversal_stage3.json
```

Exact results:

| Gate | Result |
| --- | --- |
| parser bindings/reference extraction | 140 passed |
| resolution/contracts/materialization/state | 334 passed |
| storage/service/MCP/traversal | 231 passed |
| frozen local anchor/traversal benchmarks | 15 passed |
| complete repository suite | 1,013 passed |
| dependency lock | 47 packages resolved; lock current |
| Python compileall | passed |
| targeted Stage 10 binding Pyright | 0 errors |
| package build | `loci-0.1.0.tar.gz` and `loci-0.1.0-py3-none-any.whl` built |
| diff hygiene | clean |

No test was skipped or disabled. No judge, model scorer, delegated subagent, or
paid evaluation ran.

The external frozen fixture remains exactly:

```text
c52def1bdf592ad735149d199910f74183598eccd9ccf8064335fa0cd0e84e27
```

The benchmark returned the same expected Markdown traversal results; Stage 10
did not copy its identifiers into production source or modify the fixture.

## Production MCP acceptance repositories

The final harness command was:

```bash
.venv/bin/python /tmp/loci-stage10-acceptance.py
```

It launched the installed `/Users/brummerv/.local/bin/loci-mcp` wrapper in
separate real stdio processes. Disposable repositories and isolated caches
lived under `/tmp/loci-stage10-review-20260720`; they are evidence fixtures and
are not part of the repository.

Every healthy fixture called `loci_graph_health`, `loci_graph_imports`,
`loci_graph_references`, outgoing and incoming reference-only traversal,
`loci_graph_paths`, `loci_get`, `loci_graph_neighbors`, and `loci_verify` from a
fresh process. Python also proved exact structured errors for invalid file,
status, offset, and limit inputs.

| Fixture | Imports R/U | References R/U | Verify | Fresh read | No-op incremental | Index SHA-256 |
| --- | ---: | ---: | ---: | --- | --- | --- |
| Python aliases/module/re-export/shadow/missing/decoy | 4 / 1 | 3 / 2 | 13 / 13 | hash + mtime unchanged | 5 files skipped; byte-identical | `e50f84a046a796749a215fafc6d226a6ab8e9d9026acb5af7cecf8e3253f2ff6` |
| JS/TS workspace/default/named/type/namespace/barrel/conflict/decoy | 8 / 0 | 4 / 2 | 14 / 14 | hash + mtime unchanged | 7 files skipped; byte-identical | `9c378790beaef798ca096d0cd3f228bb30bf4920662d678329bf6841483c4549` |
| Go workspace/module/replacement/alias/export/shadow/ambiguity | 5 / 0 | 6 / 2 | 23 / 23 | hash + mtime unchanged | 8 files skipped; byte-identical | `62ef17aae7f1b32524460190adbefb88b8d1f6263753dd1294beaeb53f17f686` |
| Cargo workspace/crate/module/alias/re-export/visibility/configuration | 12 / 1 | 3 / 3 | 16 / 16 | hash + mtime unchanged | 5 files skipped; byte-identical | `516c8ad834f2b4e70edadf6f6feabcd1e97a71ff5c5a78763a3538e4a4627a92` |
| mixed same-name cross-language adversarial repository | 5 / 1 | 5 / 1 | 22 / 22 | hash + mtime unchanged | 9 files skipped; byte-identical | `ec4d54b62e880d0fd4dd3792a414c0c25a957a62c5da1a17d2779bad7f3faeb6` |

The mixed fixture resolved only same-language pairs:
`python:.py`, `typescript:.ts`, `go:.go`, and `rust:.rs`. Its unresolved Python
import did not bind to same-named TypeScript, Go, Rust, or nested Python decoys.

Representative trusted paths were:

- Python `consumer.py::direct#function` -> `target.py::Thing#class`;
- TypeScript `apps/web/src/use.ts::build#function` ->
  `packages/core/src/model.ts::Shape#interface`;
- Go `app/alias.go::Alias#function` -> `core/pkg/model.go::Thing#type`;
- Rust `app/src/lib.rs::local#function` ->
  `app/src/local.rs::LocalThing#struct`; and
- mixed Go `go_use.go::Build#function` -> `gopkg/model.go::Thing#type`.

Each path returned the exact cached use line, incoming traversal returned the
source without reversing edge storage, `loci_get` returned the target, and
compatibility neighbors contained no reference edge.

## Mutation and freshness evidence

Each disposable repository then changed or removed source/control evidence,
ran a new incremental process, inspected the broken state, restored the
evidence, and re-ran the same checks:

| Fixture mutation | Broken R/U | Restored R/U | Outcome |
| --- | ---: | ---: | --- |
| delete/restore Python target file | 1 / 4 | 3 / 2 | unchanged sources re-resolved; decoy not selected |
| remove/restore JS workspace dependency | 0 / 6 | 4 / 2 | every package reference failed closed, then recovered |
| remove/restore Go workspace/dependency controls | 2 / 6 | 6 / 2 | contained package evidence changed without toolchain execution |
| remove/restore Cargo path dependency | 1 / 5 | 3 / 3 | same-crate reference survived; externalized targets did not |
| delete/restore mixed Python target | 4 / 2 | 5 / 1 | other languages stayed stable; no cross-language fallback |

All restored diagnostic counts exactly matched their initial fresh-process
counts. `loci_verify` passed in healthy, broken, and restored states. No
subprocess, toolchain, repository script, package manager, Git, curl, or network
tripwire fired.

## Live Loci dogfood

After the final code correction, Loci incrementally indexed its own repository
through MCP and reported:

- 2,088 indexed symbols;
- 1,943 graph edges;
- 725 import records: 399 resolved and 326 unresolved;
- 3,132 symbol-reference records: 1,124 resolved and 2,008 unresolved; and
- healthy graph status with no diagnostic.

The live `loci_graph_references` tool then inspected
`src/loci/mcp_server.py`, returned stable bounded pages, and proved real
references from `create_server` to exact service functions such as
`src/loci/service.py::index_repo#function`, with the import statement and
definition records attached as support.

## Residual limitations and next boundary

- Reference edges prove naming, not calls, runtime behavior, active build
  configuration, overloads, trait dispatch, or data flow.
- Dynamic Python exports/import hooks, JavaScript computed/dynamic/CommonJS
  behavior, Go build/cgo/platform selection, Rust macros/generated items and
  divergent configuration remain outside the trusted subset.
- External dependencies and targets absent from the indexed repository remain
  unresolved even if installed locally.
- Unsupported, shadowed, ambiguous, inaccessible, missing, and wrong-endpoint
  candidates remain records only; Loci never guesses by repository-wide name.
- The two shared reference orchestration files are at the review size signal;
  Stage 11 call semantics must live in separate owning modules.
- The repository's older full-Pyright debt remains a future code-health task;
  Stage 10 reduced rather than increased its error count.

The next graph roadmap item is Stage 11 cross-file calls only where a trusted
Stage 10 reference and static call-site syntax together identify one definite
callee. Heuristic candidates and architecture/orientation analysis remain later
opt-in stages with separate designs and owner gates.

## Rollback

Each implementation slice is an atomic direct-to-`master` commit and can be
reverted independently. Feature-level rollback removes the Stage 10 parser
models/extraction, language resolvers, reference records/edges,
service/MCP diagnostic, and documentation, then restores extractor version 9
and private graph-state schema 6. A schema mismatch safely rebuilds local
caches; there is no external migration or remote data cleanup.

Existing contains/import traversal remains the accepted fallback.

## Final review questions

- Every trusted reference follows one exact resolved import binding: **yes**.
- Target search can leave the imported endpoint/export surface: **no**.
- Shadowed, ambiguous, inaccessible, external, unsupported, or divergent
  evidence can become an edge: **no**.
- Python, JavaScript/TypeScript, Go, and Rust supported subsets have direct and
  adversarial evidence: **yes**.
- Fresh reads rewrite a current index: **no**.
- No-op incremental indexes differ from full indexes: **no**.
- Generic incoming/outgoing traversal and exact evidence paths work: **yes**.
- Compatibility neighbors widened: **no**.
- Runtime/toolchain/repository-code/network execution was added or observed:
  **no**.
- Calls, heuristics, or architecture analysis entered Stage 10: **no**.

## Final owner gate

- [x] exact implementation range and commit IDs recorded
- [x] focused tests and complete 1,013-test repository suite pass
- [x] lock, compile, build, type-boundary, and diff checks recorded honestly
- [x] frozen benchmark passes and checksum is unchanged
- [x] installed-wrapper MCP fixtures cover all supported language families
- [x] mixed same-name decoys prove no cross-language fallback
- [x] full/no-op incremental hashes match for every fixture
- [x] fresh reads preserve hash and mtime
- [x] source/control mutation and restoration re-resolve correctly
- [x] execution and network tripwires remain clear
- [x] every disposable repository passes `loci_verify`
- [x] residual limits, rollback, and the Stage 11 boundary are explicit
- [x] review packet and operator/agent documentation are ready for publication
- [ ] Vik explicitly accepts this final review packet
- [ ] governing design marks Stage 10 implemented, reviewed, and accepted

Stage 10 is implemented and engineering-reviewed. It must remain
`awaiting owner acceptance` until Vik explicitly approves this packet.
