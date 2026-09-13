# W3.4 — cross-repository use-case decision

Decision: **defer federation; no build now**.

Task `task_c9ec6f8dab01945a485822c1f4719800`, canonical Objective
`obj_0110c8712b21bdd2c12532f189d84a74` at `/Users/brummerv/loci`.
Useful workflows already involve multiple repositories. The reviewed evidence
does not establish a task needing a new Loci graph relationship across
independently indexed roots, or a benefit sufficient to scope that extension.

## Known needs and evidence

Reviewed the current Manifest, retained W4.7 catalog and relevant attempts,
existing code/wiki integration and code/spec ownership evidence, and current
root-scoped retrieval contracts at isolated source
`86bca31305defdeabd2b5d1fef247a64ddc4eec5`. An independent bounded audit checked
the retained app/library and source-snapshot topology. No new measurement,
integration, index/store migration or federation implementation was run.

| Need | Concrete evidence | Does it establish a federation build case? |
| --- | --- | --- |
| App/library | `rust_contained_optional_reexport` has root Cargo workspace controls plus `app/` and `core/` in one snapshot. The authored workspace dependency points to contained path `core`. JavaScript app/helper/barrel cases use relative imports in one root. | These are real inter-package dependencies, already handled within one index. Rust r1-B delivers 8/8 source and 2/2 relationships. No retained task indexes the components independently or requires a cross-root edge. |
| Service/schema | Go `Handle`/`Request` and callers use package-qualified routes under one module; other cases inspect authored types or imported contracts. All four Go snapshots have one `go.mod`; none exercises `go.work` or a replacement across roots. | No separate service/schema repositories, published contract/version mapping or consumer-impact question across roots is established. Package boundaries alone do not supply that requirement. |
| Code/wiki | Loci and llm-wiki have an actual provider/consumer integration. The Stage 5 record describes an external read-only wiki mirror and exact evidence validation; llm-wiki retains authority, roles, answerability and final budgets. This decision workflow itself reads Loci source and Brain separately. | Separate retrieval and consumer composition are demonstrated. No reviewed task requires a semantic edge joining a code symbol in one root to a wiki claim in another. Existing integration must not be relabelled as missing federation or reopened. |
| Code/spec | The saved North Star handoff assigns direction to conversation, work/status/evidence to the sole Manifest, and durable understanding to Brain. Notion is dated reference-only. Manifest and isolated code paths are worktrees of the same Loci Git project, with `.manifest` intentionally omitted from the development checkout. | Consulting several sources and separating worktrees is useful today. No code/spec linkage defect or task requiring federated traversal is demonstrated; do not create a second live plan or automatically import external spec authority. |

The [19-case corpus](https://github.com/Phluxxed/loci/blob/86bca31305defdeabd2b5d1fef247a64ddc4eec5/benchmarks/corpora/multilingual-context-v1/corpus.json)
uses 16 snapshots, with one named snapshot per case. The
[protocol](https://github.com/Phluxxed/loci/blob/86bca31305defdeabd2b5d1fef247a64ddc4eec5/benchmarks/comparisons/multilingual-context-workflow-v1/protocol.md)
materializes one source root and fresh index per attempt. Markdown's control is
one `guide.md`; the maintained Python task is one `_exploration_output.py`.
Neither is a code/wiki or cross-repository query test.

In the retained
[`rust_contained_optional_reexport-r1-B`](https://github.com/Phluxxed/loci/tree/86bca31305defdeabd2b5d1fef247a64ddc4eec5/benchmarks/results/multilingual-context-workflow-v1/rust_contained_optional_reexport-r1-B)
artifacts, `run.json.repo` names one snapshot and provenance contains all seven
workspace files under it. The r2-B wrong answer also occurs with 8/8 source and
2/2 relationships. It does not identify missing cross-root identity.
Go/Cargo exact control-access failures and omitted available paths retain their
W5 delivery/evaluator ownership; federation would not repair those demonstrated
same-root defects.

The [extensible retrieval design](https://github.com/Phluxxed/loci/blob/86bca31305defdeabd2b5d1fef247a64ddc4eec5/docs/design/2026-07-13-extensible-graph-retrieval-design.md#L9)
identifies llm-wiki as the first consumer; the
[Stage 5 integration record](https://github.com/Phluxxed/loci/blob/86bca31305defdeabd2b5d1fef247a64ddc4eec5/docs/plans/2026-07-13-extensible-graph-retrieval-stage-4.md#L925)
preserves that division of responsibility. The old tests exercise multiple wiki
corpora separately, not a joined cross-root graph. The saved code/spec source is
Brain `sources/loci-north-star-reference-complete-2026-09-10.md`; it preserves
Notion's dated reference role and the single shared Objective arrangement.

## Existing boundaries

[`graph_retrieve`](https://github.com/Phluxxed/loci/blob/86bca31305defdeabd2b5d1fef247a64ddc4eec5/src/loci/service.py#L1135)
accepts one repository root.
[`_load_graph_context`](https://github.com/Phluxxed/loci/blob/86bca31305defdeabd2b5d1fef247a64ddc4eec5/src/loci/service.py#L2059)
loads and validates that root's index and graph state.
[`RepositoryCatalogEntry`](https://github.com/Phluxxed/loci/blob/86bca31305defdeabd2b5d1fef247a64ddc4eec5/src/loci/storage/repository_catalog.py#L40)
validates a canonical path/cache-key association; cataloging repositories does
not establish semantic relationships between their nodes.

Go and Rust [resolution contracts](https://github.com/Phluxxed/loci/blob/86bca31305defdeabd2b5d1fef247a64ddc4eec5/README.md#L541)
support contained modules/packages/workspaces while preserving external and
unresolved boundaries. Graph evidence reads remain contained in their selected
root. The [MCP store-isolation contract](https://github.com/Phluxxed/loci/blob/86bca31305defdeabd2b5d1fef247a64ddc4eec5/docs/design/2026-07-22-mcp-harness-store-isolation.md)
binds a process to a configured store namespace; sharing a store is not authority
to join every repository, cross another host's store or infer an external target.

## Rationale and reopening condition

The strongest reason to build later is a real app/library or code/wiki change
that spans independently maintained roots. The Rust example would raise a new
identity and freshness problem if its app/core packages were indexed separately.
The known code/wiki workflow may likewise benefit from explicit cross-root
links. Those are plausible extensions, but the reviewed tasks do not establish
that topology, its missing relationship or an advantage over separate reads.

Reopen for a concrete answer/edit requiring an evidenced cross-repository
relationship: identify the roots, what fact links them, and why existing
single-root retrieval plus explicit composition is insufficient or materially
costly. The evidence currently lacks a qualifying unified-result task and
cross-root authority/version/freshness expectations. This is a bounded
insufficient-evidence judgment, not proof federation has no future value.

Only if a build is justified, separately agree repository identities,
permissions/ownership, freshness and version skew, unresolved external
boundaries, evidence/hop budgets and acceptance. Preserve single-repository
semantics. No global search, implicit root discovery, new access permission,
external dependency ingestion or detailed federation design follows this defer.

## Closure and next work

The known-needs review and decision criteria are satisfied; the build-only
design criterion is inapplicable. Acceptance is the bounded topology/source
audit, Manifest criterion/reference readback and scoped diff checks. All four
W3 capability decisions are now complete as defer/no-change. Their individual
limitations remain recorded; this does not certify universal product coverage.

Next: **W5.1 — truthful exact retrieval of resolver control files**,
`task_1e585a3ff7bc30b6b2dc90d5d768925a`. This is concrete delivery work for
contained `go.mod` and `Cargo.toml`, including normal MCP and future adapter
access. It is not started by this decision. W1/W2/W4 and all 114 frozen outcomes
remain unchanged; integration and installed-runtime promotion retain their
explicit direction gates.
