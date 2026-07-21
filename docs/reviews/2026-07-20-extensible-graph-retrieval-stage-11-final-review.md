# Final Review: Extensible Graph Retrieval Stage 11 — Trustworthy Calls

- **Status:** accepted by engineering review and owner
- **Date:** 2026-07-21
- **Repository:** `/Users/brummerv/loci`
- **Governing plan:** `docs/plans/2026-07-20-extensible-graph-retrieval-stage-11-trustworthy-calls.md`
- **Accepted predecessor:** `28383a5` (Stage 10 accepted)
- **Reviewed implementation head:** `2ba9f6c`
- **Reviewed commit range:** `28383a5..2ba9f6c`
- **Frozen benchmark:** `/Users/brummerv/llm-wiki/tests/fixtures/graph_shape_traversal_stage3.json`
- **Frozen SHA-256:** `c52def1bdf592ad735149d199910f74183598eccd9ccf8064335fa0cd0e84e27`

## Owner-level outcome

Loci can now prove that one indexed function or file definitely calls another
indexed function or method. It supports a conservative local subset in Python,
JavaScript/TypeScript, Go, and Rust, including direct same-file calls and
cross-file calls whose imported target was already proved by Stage 10.

In plain terms, an agent can ask “what does this function definitely call?”,
“what definitely calls this function?”, or “show me the exact source line that
proves this call?” The ordinary traversal and path tools can follow the new
relationship in either direction and fetch the target source.

Loci does not guess. Dynamic dispatch, constructors, callable values, computed
members, overload selection, macros, reflection, ambiguous names, shadowed
bindings, unsupported configuration, and external code are never treated as
proven and create no trusted edge. An unresolved call is evidence that Loci
could not prove the target, not evidence that the source is invalid.

## Delivered contract

The implemented path is:

```text
tree-sitter call syntax
  -> exact call/callee span and executable caller ownership
  -> bounded lexical binding candidates
  -> one exact same-file callable OR one resolved Stage 10 symbol reference
  -> strict current-source validation
  -> validated CallRecord
  -> directed loci:calls edge with exact or import-resolved resolution
```

Module-level calls belong to the file node. Named nested functions retain their
own symbol identity. A proven recursive call may materialize a self-edge; every
other graph self-edge remains invalid. Repeated call sites retain separate
diagnostic records while equivalent graph relationships deduplicate
deterministically.

The public diagnostic API is:

```python
graph_calls(
    repo,
    *,
    file=None,
    status="all",       # all | resolved | unresolved
    offset=0,
    limit=100,          # 1..500
    ensure_fresh=False,
)
```

The MCP surface adds exactly one tool with five user inputs:

```text
loci_graph_calls(repo, file=None, status="all", offset=0, limit=100)
```

It delegates with `ensure_fresh=True` through the existing structured
`LociError` adapter. File filtering precedes counts, status filtering precedes
pagination, and records sort stably by source position and identity. Existing
generic traversal and path APIs consume the standard edges.
`loci_graph_neighbors` remains contains-only, and no call CLI exists.

Persistence versions at the reviewed head are:

- public graph schema: 1;
- outer index schema: 5;
- private graph-state schema: 8; and
- extractor version: 11.

Older private state or extractor versions rebuild through the existing version
check. No compatibility shim, remote migration, dependency, or public schema
change was introduced.

## Supported language boundary

### Python

Direct identifier and supported attribute calls can resolve to one lexically
visible same-file function or method, or through one exact Stage 10 imported
symbol reference. Parameters, assignments, nested scopes, imports, and other
bindings suppress shadowed candidates. Decorators, defaults, lambdas, module
initialization, nested named functions, and recursion have explicit ownership
coverage.

### JavaScript and TypeScript

Direct identifier and supported member calls can resolve through current
lexical declarations or supported Stage 10 imports, aliases, namespaces, and
workspace/package paths. Named functions, methods, arrow functions, anonymous
functions, nested calls, and file initialization have explicit ownership
coverage. Computed members, optional calls, constructors, callable variables,
and ambiguous exports do not become trusted edges.

### Go

Direct identifier and package-selector calls can resolve to one callable in the
same package or through supported Stage 10 module/workspace/replacement import
evidence. Functions, methods, receiver ownership, aliases, and package
initialization are covered. Type conversions, receiver dispatch, interfaces,
callable variables, external modules, and ambiguous alternatives fail closed.

### Rust

Direct identifier and supported scoped calls can resolve through accepted
same-crate, module, re-export, workspace, package, path-dependency, visibility,
edition, and convergent configuration evidence. Functions, methods as owners,
closures, nesting, recursion, and module initialization are covered.
Constructor-like syntax, field-method dispatch, traits, associated-item
ambiguity, macros, generated code, external crates, and divergent
configuration do not become trusted edges.

The governing plan records the official Python call and binding semantics,
ECMAScript call/declaration semantics, Go call and scope rules, and Rust call,
method, name-resolution, and scope references used to set these boundaries.

Installed acceptance versions were:

- Python 3.14.5;
- `tree-sitter-language-pack` 0.13.0;
- MCP 1.28.0;
- Loci 0.1.0; and
- Pyright 1.1.410.

## Implementation commits

| Commit | Purpose |
| --- | --- |
| `f37cfd0` | approve and freeze the detailed Stage 11 plan |
| `51157c7` | extract shared lexical binding context |
| `ac89120` | extract bounded call sites |
| `98dca26` | index named nested callables |
| `454ddc0` | resolve exact same-file calls |
| `817846b` | resolve imported calls exactly |
| `b496ba7` | validate trusted call edges |
| `5bd2f2b` | integrate calls into graph materialization |
| `94bb6e1` | persist validated call records |
| `43c64cf` | refresh persisted calls incrementally |
| `bc487f1` | validate persisted state on fresh reads |
| `65fd917` | prove fresh-process call validation |
| `867a0e6` | expose bounded call diagnostics |
| `bc67c60` | expose the MCP call diagnostic |
| `f2c52d4` | make caller-ownership type boundaries exact |
| `1e77354` | require the real installed Loci wrapper in MCP tests |
| `2ba9f6c` | type the shared parser-language fixture exactly |

The reviewed range changes 33 files: 8,434 insertions and 674 deletions. The
governing plan contributes substantial documentation; production work is split
across binding/ownership extraction, call extraction, call resolution,
validation/materialization, persistence/freshness, and the additive service/MCP
reader.

This packet plus README, skill, plan, and design status edits are
publication-only changes after `2ba9f6c`; they do not widen runtime behavior.

## Five-axis code review

Review result: two required acceptance findings and one Stage 11-owned typing
regression were corrected before this packet. No open Critical or Required
correctness, security, architecture, performance, or compatibility finding
remains.

### Correctness

Tests cover exact Unicode-safe source spans, syntax shapes, strict limits,
ownership, lexical shadowing, local and imported resolution, recursion,
language-specific controls, strict records, current hashes, edge validation,
persistence, incremental re-resolution, fresh-process reads, diagnostic
filters, traversal, paths, cycles, budgets, and deterministic ordering.

Every trusted imported call must join the call's exact callee span to one
current resolved Stage 10 symbol reference. Every trusted local call must have
one supported visible callable candidate. Validation checks current source,
caller, target, support, and endpoint kinds before materialization.

### Readability and architecture

Shared lexical ownership lives in `_binding_context.py`; call syntax lives in
`parser/calls.py`; strict call records and cross-language orchestration live in
`graph/calls.py`; final trust checks live in `_call_validation.py`; service and
MCP layers only read and serialize validated current state.

The file-size review signal was inspected explicitly:

- `src/loci/parser/_binding_context.py`: 865 lines;
- `src/loci/parser/calls.py`: 299 lines;
- `src/loci/graph/calls.py`: 1,044 lines;
- `src/loci/graph/_call_validation.py`: 672 lines; and
- `src/loci/service.py`: 1,713 lines.

`graph/calls.py` remains a cohesive strict-record and resolution orchestrator,
with final validation already separated. `service.py` was large before this
stage and received one additive bounded reader. No acceptance refactor is
justified by the reviewed behavior.

### Security

Repository source and control files remain untrusted input. Existing path,
real-path containment, regular-file, byte/count/depth, strict decoding,
source-hash, schema, and diagnostic-redaction boundaries apply before a record
becomes trusted state. Parser and resolver work is bounded by existing file and
candidate limits; the MCP diagnostic returns at most 500 records.

Static scans found no subprocess, shell, socket, HTTP-client, or network
execution path in the new production code. The disposable acceptance harness
blocked Python subprocess and shell APIs, blocked IPv4/IPv6 sockets and name
resolution, placed failing toolchain/package-manager/Git/network/model shims
first on `PATH`, and included repository code that raises if executed. No
tripwire fired.

No dependency changed, no frozen benchmark identifier appears in production
source, and no secret-like material is added by the Stage 11 range.

### Performance

Call extraction reuses each file's existing tree. Resolution builds bounded
frozen indexes, joins only exact recorded evidence, and preserves deterministic
ordering. Diagnostic reads perform one current persisted-state scan and bounded
serialization.

No-op incremental fixture runs skipped both source files and produced
byte-identical indexes. Fresh reads preserved serialized hash and mtime. The
live repository also preserved its hash and mtime across a fresh-process read.

### Compatibility

The installed server advertises 19 tools, with `loci_graph_calls` exactly once
and only the planned five inputs. Public graph schema 1, outer index schema 5,
existing imports/references, search, outline, exact reads, health, anchors,
traversal, paths, retrieval, and contains-only compatibility neighbors remain
green. No CLI, model, judge, external toolchain, or dependency was added.

## Review-discovered corrections

The final review found and fixed three issues before publication:

1. Pyright exposed imprecise optional-span handling in executable-owner
   selection and loose test fixture types. `f2c52d4` and `2ba9f6c` make those
   Stage 11-owned boundaries exact.
2. The installed-wrapper MCP test used `shutil.which("loci-mcp")`. Under
   `uv run` that selected `.venv/bin/loci-mcp`, so it did not prove the claimed
   user-installed path. `1e77354` now requires
   `/Users/brummerv/.local/bin/loci-mcp`, proves it resolves through the shared
   repository wrapper, and launches from the repository root.
3. A detached, environment-matched Stage 10 baseline reported 262 full-repo
   Pyright errors. After the fixes, the Stage 11 head also reports 262. The
   stage therefore adds zero errors to the existing non-gate type debt; its new
   targeted production boundaries report zero errors.

The production harness itself had three false starts that were corrected before
evidence was accepted. It first selected a call inside an anonymous lambda,
then a local helper declared later than the accepted lexical visibility/order,
and then read `support_kind` from the wrong response level. The final live
dogfood instead selects the genuine module-level `mcp = create_server()` call
and checks the actual response schema. These were harness mistakes, not product
changes, and are recorded to avoid presenting only the successful attempt.

## Repository verification evidence

The focused and complete gates were:

```bash
uv run pytest -q tests/parser/test_references.py tests/parser/test_calls.py

uv run pytest -q \
  tests/graph/test_calls.py \
  tests/graph/test_call_contracts.py \
  tests/graph/test_materialize.py \
  tests/graph/test_state.py \
  tests/graph/test_traversal.py

uv run pytest -q \
  tests/storage/test_index_store.py \
  tests/storage/test_call_index_store.py \
  tests/test_call_service.py \
  tests/test_call_mcp.py \
  tests/test_service.py \
  tests/test_mcp_server.py

uv run pytest -q \
  tests/graph/test_anchor_benchmark.py \
  tests/graph/test_traversal_benchmark.py

uv run pytest -q tests/
uv lock --check
uv run python -m compileall -q src tests
uv build
git diff --check
shasum -a 256 \
  /Users/brummerv/llm-wiki/tests/fixtures/graph_shape_traversal_stage3.json
```

Exact results before the final publication-only commit:

| Gate | Result |
| --- | --- |
| parser references/calls | 116 passed |
| graph calls/contracts/materialization/state/traversal | 287 passed |
| storage/service/MCP matrix | 184 passed |
| frozen local anchor/traversal benchmarks | 15 passed |
| complete repository suite | 1,185 passed |
| affected review-fix tests | 114 passed, then 69 passed |
| dependency lock | 47 packages resolved; lock current |
| Python compileall | passed |
| targeted Stage 11 Pyright | 0 errors |
| full Pyright baseline/current | 262 / 262 errors; net zero |
| package build | `loci-0.1.0.tar.gz` and `loci-0.1.0-py3-none-any.whl` built |
| diff hygiene | clean |

The complete suite passed again after the first two review corrections and a
final time after the last test-only typing correction: 1,185 passed in 55.31
seconds. No test was skipped or disabled. No judge, model scorer, delegated
subagent, or paid evaluation ran.

The external frozen fixture remained exactly:

```text
c52def1bdf592ad735149d199910f74183598eccd9ccf8064335fa0cd0e84e27
```

## Production MCP acceptance repositories

The final disposable-repository harness launched the exact installed
`/Users/brummerv/.local/bin/loci-mcp` wrapper in separate real stdio processes.
Each language used a full index process and a distinct fresh read process. It
listed all 19 tools, queried `loci_graph_calls`, traversed calls outgoing and
incoming, checked contains-only compatibility neighbors, ran graph health and
`loci_verify`, preserved hash and mtime on a fresh read, and produced a
byte-identical no-op incremental index.

Each fixture contained one trusted call and one deliberately unsupported
repository-code tripwire. The file-filtered query returned exactly the trusted
resolved call; health retained both outcomes so the unsupported site stayed
inspectable and unresolved.

| Fixture | Calls R/U | Verify | Fresh read | No-op incremental | Index SHA-256 |
| --- | ---: | ---: | --- | --- | --- |
| Python | 1 / 1 | 4 / 4 | hash + mtime unchanged | 2 files skipped; byte-identical | `4f1344341d2324495d9e3b16b6da4caf1216fd0e09993563543459eac77a2fde` |
| JavaScript/TypeScript | 1 / 1 | 4 / 4 | hash + mtime unchanged | 2 files skipped; byte-identical | `a464e284604bcdc705fff919b957e4f0489d52b148386a18244ea027cf5196a9` |
| Go | 1 / 1 | 5 / 5 | hash + mtime unchanged | 2 files skipped; byte-identical | `9ce84ea74510530d625fd148b01638961f8a4c2e05f9388b4f9647e378f4a404` |
| Rust | 1 / 1 | 5 / 5 | hash + mtime unchanged | 2 files skipped; byte-identical | `e295df5d01b386c93b06726f552871952846c4e5bca484722c44e71c2699712a` |

All trusted calls reported exact source evidence and the expected resolution.
All unresolved tripwire calls created no edge. No subprocess, compiler,
interpreter, repository script, package manager, Git, curl, model, judge, or
network tripwire fired.

## Live Loci dogfood

The same exact installed wrapper created an isolated fresh index of Loci's own
repository, then a separate process read it back. It reported:

- 2,333 indexed symbols;
- 2,616 graph edges;
- 814 import records: 458 resolved and 356 unresolved;
- 3,549 symbol-reference records: 1,303 resolved and 2,246 unresolved; and
- 8,875 call records: 617 resolved and 8,258 unresolved.

The live `loci_graph_calls` query filtered `src/loci/mcp_server.py` to resolved
records and selected the exact module-level relationship:

```text
src/loci/mcp_server.py::__file__#file
  -- loci:calls / exact, evidence: mcp = create_server() -->
src/loci/mcp_server.py::create_server#function
```

The filtered file contained 73 call records: 2 resolved and 71 unresolved. The
response returned the 2 resolved records in stable order. `loci_verify` checked
all 2,333 symbols with no failure. A fresh read preserved index hash
`2482057cf859a903910297d17535a8bd5800b6e5de3e9eb4027079a486a297d6`
and mtime, and no execution or network tripwire fired.

The MCP process attached to the already-running agent session predates the new
tool and must be restarted before that session advertises
`loci_graph_calls`. This is host process lifetime, not a product failure; the
fresh installed-wrapper processes above are the production acceptance path.

## Residual limitations and next boundary

- Trusted calls cover only exact same-file and exact Stage 10 import-resolved
  targets in the documented local subset.
- Constructors, dynamic/computed/optional calls, callable variables and fields,
  receivers, interfaces, traits, virtual dispatch, overloads, macros,
  reflection, generated code, external targets, type-only/non-callable targets,
  ambiguous/shadowed evidence, and divergent configuration remain outside the
  trusted subset and create no edge.
- Same-file calls outside accepted lexical visibility and declaration-order
  evidence remain unresolved; Loci does not use repository-wide name guessing.
- Calls prove a static source relationship, not runtime execution frequency,
  reachability, behavior, data flow, or architecture.
- Call diagnostics are MCP/service-only. No call CLI exists.
- Existing full-repository Pyright debt remains a separate code-health task;
  Stage 11 adds no net errors against the matched accepted baseline.

Later heuristic candidates and architecture/orientation analysis remain
separate opt-in roadmap stages with their own designs and owner gates.

## Rollback

Each implementation slice is an atomic direct-to-`master` commit and can be
reverted independently. Feature-level rollback removes Stage 11 call
extraction, resolution, records/edges, persistence/freshness integration,
service/MCP diagnostics, and documentation, then restores extractor version 10
and private graph-state schema 7. A schema mismatch safely rebuilds local
caches; there is no external migration or remote data cleanup.

Stage 10 resolved references and existing contains/import traversal remain the
accepted fallback.

## Final review questions

- Every trusted imported call joins one exact resolved Stage 10 reference:
  **yes**.
- Every trusted local call has one exact visible callable target: **yes**.
- Ambiguous, shadowed, dynamic, unsupported, external, or divergent evidence
  can become an edge: **no**.
- Python, JavaScript/TypeScript, Go, and Rust have direct production evidence:
  **yes**.
- Fresh reads rewrite a current index: **no**.
- No-op incremental indexes differ from full indexes: **no**.
- Generic incoming/outgoing traversal and exact evidence paths work: **yes**.
- Compatibility neighbors widened: **no**.
- Runtime/toolchain/repository-code/network/model/judge execution was added or
  observed: **no**.
- Constructors, dispatch, data flow, or architecture analysis entered Stage 11:
  **no**.

## Final owner gate

- [x] exact implementation range and commit IDs recorded
- [x] focused tests and complete 1,185-test repository suite pass
- [x] lock, compile, build, type-boundary, baseline, and diff checks recorded
- [x] frozen benchmark passes and checksum is unchanged
- [x] exact installed-wrapper MCP fixtures cover all four language families
- [x] full/no-op incremental hashes match for every fixture
- [x] fresh reads preserve hash and mtime
- [x] live Loci dogfood proves a real call in this repository
- [x] execution, repository-code, network, model, and judge tripwires remain clear
- [x] every disposable repository and the live index pass `loci_verify`
- [x] residual limits and rollback are explicit
- [x] review packet and operator/agent documentation are ready for publication
- [x] Vik explicitly accepts this final review packet
- [x] governing design marks Stage 11 implemented, reviewed, and accepted

Vik explicitly accepted this packet on 2026-07-21. Stage 11 is implemented,
engineering-reviewed, owner-accepted, and closed.
