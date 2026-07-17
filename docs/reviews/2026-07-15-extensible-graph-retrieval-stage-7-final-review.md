# Extensible Graph Retrieval Stage 7 Final Review

**Status:** Accepted under the owner's delegated review gate

**Recommendation:** Accept

**Review date:** 2026-07-17

**Owner authorization:** The owner authorized autonomous completion through
`/goal` and established that substantial work may be reviewed, committed, and
pushed when Codex finds it acceptable

**Repository:** `/Users/brummerv/loci`

**Implementation baseline:** `1c2e67efdd132c498b3f36def895c9f9d3aedd92`

**Reviewed implementation and documentation head:**
`2e880d9029d1dbe57d52318cbb35c7faf2ebd7ad`

**Canonical plan:** [Extensible Graph Retrieval Stage 7 — Module-aware Go
Import Resolution](../plans/2026-07-15-extensible-graph-retrieval-stage-7-go-import-resolution.md)

## Decision recorded

Accept Stage 7 as shipped through
`2e880d9029d1dbe57d52318cbb35c7faf2ebd7ad`.

No critical or required change remains. The implementation meets the accepted
contract: Loci parses bounded repository-contained Go module controls without
running Go or repository code, constructs stable package nodes, resolves only
the conservative supported local module relationships, materializes validated
file-to-package dependency edges, and exposes them through the existing MCP and
generic traversal surfaces. Python, JavaScript, TypeScript, Markdown, graph
extension, and exact-navigation contracts remain compatible. Rust remains
deliberately unresolved.

The owner asked `/goal` to complete the accepted plan without further
interaction and had already established a standing rule that substantial work
should be committed and pushed when Codex's review is satisfied. This packet is
therefore the delegated final gate rather than a claim that the owner manually
read this document before publication.

This acceptance closes Stage 7. It does not authorize resolved symbol
references, cross-file calls, heuristic default edges, architecture analysis,
or Cargo-aware Rust resolution.

## Scope under review

The review covers the following 14 commits after the accepted Stage 7 plan:

| Task | Commit | Change |
| --- | --- | --- |
| 1 | `0ee64adb9c5872df942600e88b0a4c1f8946a013` | `feat: parse Go module control files` |
| 1 | `14cf78f01e38bd042c5cd506abfd65293c0cebf3` | `feat: harden Go control parser boundaries` |
| 2 | `b89a11bddc3b816d1b92c359541d9ea1ab10ddcf` | `feat: extract Go package declarations` |
| 2 | `9915f8ac756e0e1c26781c41a7f3e533437794c5` | `feat: build Go package indexes` |
| 2 | `ead5705d9ec5d3a42cb3275390e86c43c296ba49` | `fix: reject noncanonical Go file nodes` |
| 2 | `28161c635977ddddef416b4d104302e355d72050` | `perf: bound Go package construction` |
| 3 | `7ce77070895b8b78a526147027920439c49a1ad1` | `feat: distinguish import target kinds` |
| 3 | `77c751901f8e4d3a69f6a648d8d95d36cabd7331` | `feat: resolve Go imports to packages` |
| 3 | `d09e819989e2862b744ab222035aafa58a352774` | `test: expect schema 3 import targets` |
| 4 | `66db9f777c8d77e87d7e81a95875af69eec64a55` | `feat: materialize Go package import edges` |
| 5 | `1eeea6d8954725e118fec44db254c392c2fdd53b` | `feat: integrate Go package indexing` |
| 6 | `e4d68578e073455056357dd3ab9c9cc2f770f4e3` | `feat: expose Go package import targets` |
| 7 | `a6a2945cdbda43b971764f744075218d2100e314` | `fix: verify Go package anchor nodes` |
| 8 | `2e880d9029d1dbe57d52318cbb35c7faf2ebd7ad` | `docs: publish Go import resolution contract` |

The baseline-to-reviewed-head diff contains 21 changed files, 4,902 insertions,
and 117 deletions. It does not change project dependencies or lockfile
resolution.

## Verification summary

| Check | Result |
| --- | --- |
| Final Stage 7 compatibility and adversarial slice | 371 passed in 9.29 seconds; 9.55 seconds wall time |
| Task 7 full Loci suite | 590 passed in 32.73 seconds |
| Final reviewed-head full Loci suite | 590 passed in 34.48 seconds; 34.75 seconds wall time |
| Final source distribution and wheel build | Passed in 0.89 seconds wall time |
| Real-repository full and incremental index | Passed; healthy and deterministic |
| Installed-wrapper fresh-process MCP review | Passed |
| Package-anchor content verification | 599 checked, 599 passed |
| Loci skill mirror | Byte-identical |
| `git diff --check` | Passed |
| Frozen benchmark checksum | Unchanged |
| Model judge invocations | None |

The final full-suite command, run at reviewed head
`2e880d9029d1dbe57d52318cbb35c7faf2ebd7ad`, was:

```text
/usr/bin/time -p .venv/bin/python -m pytest tests/ -q
```

It returned:

```text
590 passed in 34.48s
real 34.75
user 14.67
sys 6.54
```

The focused Stage 7 command was:

```text
/usr/bin/time -p .venv/bin/python -m pytest \
  tests/parser/test_imports.py \
  tests/graph/test_go_modules.py \
  tests/graph/test_imports.py \
  tests/graph/test_contracts.py \
  tests/graph/test_materialize.py \
  tests/graph/test_state.py \
  tests/graph/test_traversal.py \
  tests/storage/test_index_store.py \
  tests/test_service.py \
  tests/test_mcp_server.py -q
```

It returned:

```text
371 passed in 9.29s
real 9.55
user 5.22
sys 1.91
```

Packaging used:

```text
/usr/bin/time -p uv build
```

It produced both `dist/loci-0.1.0.tar.gz` and
`dist/loci-0.1.0-py3-none-any.whl` and returned:

```text
real 0.89
user 0.34
sys 0.24
```

Documentation hygiene used:

```text
diff -u skills/loci/SKILL.md .claude/skills/loci/SKILL.md
git diff --check
```

Both commands returned no output and status zero.

## Frozen benchmark policy

The frozen benchmark remains:

```text
/Users/brummerv/llm-wiki/tests/fixtures/graph_shape_traversal_stage3.json
SHA-256: c52def1bdf592ad735149d199910f74183598eccd9ccf8064335fa0cd0e84e27
```

The benchmark itself was not run. Its approved trigger is focused evidence of
Markdown ID, anchor, traversal, path, retrieval, or adapter drift. No such
evidence appeared: Stage 7 tests, the full suite, exact-neighbor compatibility,
fresh-process MCP calls, and graph determinism all remained green. No model
judge was invoked.

## Public contract and schema review

Stage 7 is additive at the public boundary:

| Contract | Before | After | Review result |
| --- | ---: | ---: | --- |
| Index storage schema | 5 | 5 | No storage-envelope migration |
| Extractor version | 5 | 6 | Existing extraction metadata is rebuilt |
| Public graph/MCP envelope schema | 1 | 1 | Tool envelopes and registrations remain compatible |
| Persisted graph-state schema | 2 | 3 | Old derived graph state is rejected and rebuilt |
| `loci_graph_imports` input | Existing five fields | Unchanged | Installed MCP schema preserved |

Every import item now includes `target_kind` and `target_package`:

- Python and JavaScript/TypeScript resolved records use
  `target_kind="file"`, keep `target_file`, and set `target_package=null`.
- Go resolved records use `target_kind="package"`, set `target_file=null`, and
  expose the effective import path in `target_package`.
- Unresolved records set all target fields to null and retain one explicit
  `unresolved_reason`.

Go package nodes are stable zero-width `kind="package"` symbols. Their ID is
`<repository-relative-directory>::<effective-import-path>#package`. A
deterministic non-test source file anchors outline, retrieval, hashing, and
verification, but neither the anchor nor its filename is presented as the
import target. Generic node references add validated `directory`,
`import_path`, and `package_name` attributes only for these nodes.

`index_repo()` and `loci_graph_health` add
`graph_go_packages_indexed`. Existing counts, pagination, error envelopes, MCP
registration, and tool input signatures remain intact. No Go-specific MCP or
CLI command was added.

## Supported and deliberately unsupported Go semantics

The accepted resolver supports:

- a source file's deepest valid contained module;
- packages in that same module;
- modules explicitly activated by the nearest contained `go.work` that also
  includes the source module;
- contained local replacements backed by a direct explicit requirement;
- wildcard replacements and exact version-specific replacements when the
  direct versions agree and are not excluded;
- workspace replacement precedence over module replacement;
- nested-module ownership and the Go `internal` visibility boundary; and
- stable package identity across anchor-file replacement.

The resolver deliberately does not:

- invoke `go`, execute repository code, inspect `GOPATH` or `GOMODCACHE`, read
  `GOWORK`, contact a proxy, or download a dependency;
- inherit an ambient parent workspace or follow a control path outside the
  repository;
- implement minimal version selection or load a transitive module graph;
- follow remote replacements or model vendor mode;
- evaluate build tags, platform or architecture constraints, or cgo;
- make `package main`, invalid/conflicting declarations, test-only directories,
  or vendor directories import targets; or
- resolve Rust/Cargo imports.

Normal unsupported, external, missing, invalid, ambiguous, and inaccessible
outcomes remain bounded diagnostic records without edges. Unsafe or malformed
contained controls and package-index invariant failures produce structured
diagnostics; internal contract failures abort the atomic index replacement.

## Purpose-built fresh-process MCP review

The final adversarial harness used an ephemeral repository outside Loci's test
tree and an isolated cache. It contained:

- one root module and a multi-file internal package;
- one omitted nested module;
- two active workspace modules;
- one direct local replacement;
- standard-library, remote, missing, and inaccessible imports;
- a same-name decoy directory;
- Python, TypeScript, and Rust sources alongside Go.

Fresh sessions invoked the installed `loci-mcp` wrapper rather than service
functions in-process. The persisted graph digest was identical across fresh
processes:

```text
8e0a4cdce8b57e6d9be3bffca1d2f097f05e5b31cff981316e767b43effaa56a
```

The result was:

| Measurement | Value |
| --- | ---: |
| File nodes | 14 |
| Go package nodes | 5 |
| Import observations | 11 |
| Resolved observations | 5 |
| Unresolved observations | 6 |
| Materialized import edges | 5 |
| Graph diagnostics | 0 |
| Graph status | Healthy |

Language outcomes were three resolved and five unresolved Go imports, one
resolved Python import, one resolved TypeScript import, and one unresolved Rust
import. Go's unresolved reasons were `external` (3), `inaccessible` (1), and
`not_indexed` (1).

The three Go targets were exactly:

```text
internal/store::example.com/root/internal/store#package
replacement/dep/client::example.com/dep/client#package
work/lib/pkg::example.com/lib/pkg#package
```

The same-name decoy was ignored. Traversal returned package attributes, and
path evidence pointed to the exact import statement in `cmd/server/main.go` at
line 5. The compatibility `loci_graph_neighbors` call remained empty. Search
and exact navigation continued to work.

The fresh installed process advertised `loci_graph_imports` with exactly the
input properties `file`, `limit`, `offset`, `repo`, and `status`, with only
`repo` required. All resolved Go items were independently asserted to have
`target_kind="package"`, `target_file=null`, and a non-empty
`target_package`.

## Real-repository review

The review used a shallow clone of
[`google/go-cmp`](https://github.com/google/go-cmp) at immutable commit:

```text
b133f1f1932e48f466f597a3346ce6f5a49a0dc1
2026-06-18T00:33:21-07:00
Replace interface{} with any (Go 1.18+) (#395)
```

Network access was used only to create that review clone. Loci's indexing and
all automated tests used no network and did not require a Go executable.

| Measurement | Full index | No-change incremental |
| --- | ---: | ---: |
| Wall time | 0.55 seconds | 0.48 seconds |
| Symbols | 599 | 599 |
| File nodes | 32 | 32 |
| Go package nodes | 10 | 10 |
| Imports | 100 | 100 |
| Resolved imports | 22 | 22 |
| Unresolved imports | 78 | 78 |
| Edges | 26 | 26 |
| Health | Healthy | Healthy |

All 22 resolved Go imports targeted package nodes. All 78 unresolved imports
were external, which is expected for standard-library and remote dependencies.
One inspected edge ran from
`cmp/cmpopts/equate.go::__file__#file` to
`cmp::github.com/google/go-cmp/cmp#package`. The target exposed
`directory="cmp"`, `import_path="github.com/google/go-cmp/cmp"`, and
`package_name="cmp"`, with `cmp/compare.go` as its deterministic anchor. Exact
path evidence retained the import at line 15.

The package target had five incoming importers. A bounded transcript returned
two and correctly reported three omitted by the requested maximum. The
compatibility neighbor API again returned no import edges. After the package
anchor verifier correction, `loci_verify` checked all 599 symbols and passed all
599.

## Loci self-index and performance

An isolated full and no-change incremental index of Loci itself produced:

| Measurement | Full index | No-change incremental |
| --- | ---: | ---: |
| Wall time | 1.30 seconds | 1.10 seconds |
| Symbols | 1,279 | 1,279 |
| File nodes | 28 | 28 |
| Go package nodes | 0 | 0 |
| Imports | 347 | 347 |
| Resolved imports | 160 | 160 |
| Unresolved imports | 187 | 187 |
| Edges | 695 | 695 |
| Health | Healthy | Healthy |

The full and incremental persisted graph counts and digest matched. This
repository has Go fixtures but no importable Go module package, so zero Go
package targets is the truthful result.

A non-blocking output inconsistency remains outside the graph contract:
`index_repo().languages` describes files processed during a full run but also
includes skipped files during a no-change incremental run. The Loci and
`go-cmp` language summary therefore differed between modes even though symbols,
package nodes, imports, edges, graph digest, and health were identical. This is
not Stage 7 graph drift, but the summary field should be clarified or normalized
in a separate change.

## Incremental and determinism evidence

Automated tests and the isolated harness prove that unchanged source imports
are re-resolved after:

- adding or deleting a nested module control;
- adding or removing a workspace `use` entry;
- adding or removing a local replacement;
- adding or deleting a target package; and
- deleting the final target file.

Raw import extraction can be retained for unchanged files, while module
context, bindings, package nodes, resolved records, and graph edges are rebuilt
from the current complete repository view. Control hashes participate in graph
freshness. Index replacement remains atomic.

Package IDs survive deletion of the old lexicographically first anchor file.
The anchor path and content hash move to the next file. Task 7 caught and fixed
one real verifier defect here: zero-width package symbols cannot use the normal
"symbol name appears inside its byte span" check. Verification now recognizes
only fully validated Go package-node metadata and compares the whole current
anchor-file hash. The real-repository 599/599 verification result exercises the
fix.

## Compatibility review

- Python, JavaScript, and TypeScript resolved records retain file targets and
  now receive only the additive `target_kind` and `target_package` fields.
- Rust remains `unresolved/unsupported_language` and edge-free.
- Markdown page/section IDs and containment behavior are unchanged.
- `loci_graph_neighbors` remains exact outgoing `loci:contains` only; docs tell
  agents to use filtered traversal or paths for imports.
- Safe generic traversal continues to admit `exact`, `declared`, and
  `import-resolved`, never `heuristic` implicitly.
- Public graph contribution schema version 1, MCP tool registration, input
  schemas, pagination, and structured errors remain stable.
- `search`, `outline`, `get`, path evidence, graph health, and installed-wrapper
  fresh-process calls passed.
- No new runtime dependency, Go installation, environment workspace, network
  service, or repository execution is required.

## Five-axis review

### Correctness

No blocking defect remains. The parser, binding construction, package identity,
resolution order, target-kind invariants, edge validation, persistence,
freshness, incremental rebuild, public output, and real-repository behavior are
covered. Unsupported cases remain explicit rather than guessed. The one defect
found during the final gate was reproduced, fixed at its verifier boundary, and
regressed with both focused and real-repository evidence.

### Readability and maintainability

Go control parsing, typed module/workspace models, binding construction, package
nodes, and target resolution live together in `graph/go_modules.py`. Raw syntax
extraction remains in `parser/imports.py`; language-neutral record, edge,
materialization, and service layers receive additive target-kind behavior. The
MCP layer remains a thin adapter. Strict dataclasses and validators keep
cross-layer invariants explicit.

### Architecture

The implementation preserves the graph pipeline:

```text
bounded control/source scan -> raw import and package observations
-> current module context -> stable package nodes -> deterministic resolution
-> validated built-in contribution -> materialized edge -> generic traversal
```

Package identity is separate from whichever file anchors retrieval. Raw
observations remain distinct from resolution, allowing unchanged files to be
re-resolved whenever controls or repository membership change.

### Security and trust

The indexed repository is treated as untrusted input. Control candidates are
bounded regular non-symlink files, resolved inside the repository, and parsed
without execution. Directive, binding, and package ceilings are deterministic.
Unsafe escapes and malformed contained controls surface redacted structured
diagnostics. The resolver uses exact contained bindings and never performs a
repository-wide name search. Internal invariant failure preserves the previous
valid index rather than publishing partial state.

### Performance

No material regression was found. Control discovery shares the repository scan;
unchanged file extraction is retained; package construction and every parser or
binding collection are bounded. Full and incremental measurements on both Loci
and `go-cmp` are sub-two-second in this environment, and the full 590-test suite
remains under 35 seconds.

## Findings, risks, and deviations

### Findings

- **Critical:** None.
- **Required:** None.
- **Suggestion:** Clarify or normalize the non-graph `index_repo().languages`
  summary across full and incremental modes in a separate task.

### Accepted limits and residual risks

- The pure parser intentionally implements only the official directives needed
  for local resolution. Future Go syntax can require an explicit parser update.
- No minimal version selection means ambiguous or transitive dependency cases
  remain unresolved even when the Go toolchain could select one version.
- Build constraints are not evaluated, so package presence reflects indexed
  non-test source rather than a selected platform build.
- Vendor mode and remote replacements remain outside the trusted graph.
- Package nodes are additive search/outline symbols and have no package-to-file
  membership edges in this stage.
- A long-lived host installed before these commits may require a restart; fresh
  installed-wrapper processes advertised and executed the unchanged MCP tool.
- Rust remains extract-and-report until a real consumer justifies a separate
  Cargo-aware design.

### Deviations from the accepted plan

No behavioral deviation remains. The frozen benchmark was checksum-verified but
not run, exactly as the plan requires when no compatibility trigger fires. The
real-repository target was the selected `google/go-cmp` immutable commit. The
purpose-built review harness was intentionally ephemeral; permanent behavior
coverage lives in the automated suite and this packet preserves the transcript
and measurements.

The final gate did discover the package-anchor verifier bug described above.
Fixing it within Task 7 was the accepted plan's intended purpose and did not
widen Stage 7 scope.

## Rollback

Do not edit cached graph data manually. If a blocker is later found:

1. revert the Stage 7 implementation commits from
   `0ee64adb9c5872df942600e88b0a4c1f8946a013` through
   `a6a2945cdbda43b971764f744075218d2100e314` as one feature unit;
2. revert the Stage 7 documentation commit
   `2e880d9029d1dbe57d52318cbb35c7faf2ebd7ad`;
3. reinstall Loci and run a fresh or incremental index; and
4. verify Go observations return to
   `unresolved/unsupported_language`, with no Go package nodes or Go import
   edges.

Extractor-version and graph-state checks rebuild derived cache state under the
reverted contracts. No repository source, module control, graph profile, or
extension contribution requires migration.

## Delegated owner review gate

- [x] All Task 7 compatibility and adversarial evidence passed.
- [x] Public and agent documentation distinguishes package and file targets.
- [x] Supported and unsupported Go semantics and deferred Rust behavior are
  explicit.
- [x] No documentation sends import traversal through
  `loci_graph_neighbors`.
- [x] No benchmark or model judge ran without its trigger.
- [x] Codex's five-axis review found no critical or required change.
- [x] The owner's `/goal` request and standing auto-publish rule authorize this
  delegated acceptance and direct push.

## Final verdict

**ACCEPTED.** Stage 7 is complete at the implementation, compatibility,
security, documentation, real-repository, and delegated owner-review levels.

Post-acceptance note, 2026-07-18: the acceptance verdict and Stage 7 evidence
remain unchanged. The owner later superseded the recorded follow-on order after
identifying Anvil as a definite Rust consumer. The next graph-roadmap item is
now completion of deterministic JavaScript/TypeScript repository-local
dependency resolution, followed by Cargo-aware Rust dependency resolution.
Resolved symbol references follow those dependency-layer stages. Each requires
its own design and review boundary.
