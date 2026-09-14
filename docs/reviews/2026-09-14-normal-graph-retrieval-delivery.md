# Deterministic normal graph retrieval delivery

Vik selected deterministic graph policy in ordinary retrieval. The default MCP
surface now has two operations: `loci_retrieve(repo, query, seed_ids)` and
`loci_read(repo, source_ref)`. Retrieval selects anchors and traverses supported
stored relationships in code. There is no agent-selected intent, edge family,
direction, hop count, budget or enable-graph flag. The operator can explicitly
select the legacy 21-tool catalog with `LOCI_MCP_SURFACE=diagnostic`.

## Delivered behavior

The frozen contract is in
`.scratch/deterministic-graph-retrieval/contract.md` and its companion schema.
`normal-graph-v1` uses two semantic hops, shared rounds across anchors and
families, deterministic ranking, and fixed work/source/output caps. Each emitted
relationship retains its native endpoints and complete selected source proof.
Ownership links do not count as semantic relationships or suppress a real edge
between already-selected nodes. Missing, stale, unsupported and clipped evidence
is explicit. Exact source paging preserves repository containment, indexed-input
eligibility, hash equality and UTF-8 boundaries.

Normal responses include policy execution, examined/traversed counts, delivered
relationships, exact source spans and hashes, byte accounting and omissions.
They cannot guarantee an edge for every query or exhaustive static semantics.
Swift module edges are withheld as `proof_unavailable` where complete unique
package-target declaration proof is unavailable. Source references are exact
locators; they make no issuance, authorization or prior-delivery claim.

The versioned `benchmarks/ordinary_adoption_normal.py` adapter separates public
invocations, reported traversal, validated delivered relationships, actual
model-visible delivery and answer-supported claims. It rejects missing,
duplicate or inconsistent accounting and retains errors and unknowns. Graph
counts do not establish correctness or benefit.

Shared catalog mutation now uses one advisory lock plus atomically published
owner evidence, preserving two-root concurrent writes and owner-only cleanup.
Abandoned mutation evidence still requires repair. The implementation requires
POSIX advisory locking. No live catalog was manually repaired.

Unique JavaScript/TypeScript import and re-export proof now includes the complete
statement. Verified single-line statements preserve the legacy physical line,
including its newline. Ambiguous or stale source remains refused.

## Source and installed provenance

Canonical source remains `/Users/brummerv/loci` on `master`; Manifest has one
canonical repository. Existing installations already point here:

- `~/.local/bin/loci-mcp` resolves to `.shared/loci-mcp-wrapper.sh`.
- The installed editable Python package resolves to `src/loci` in this checkout.
- `~/.codex/skills/loci` resolves to `skills/loci` in this checkout.
- Repository `.claude/skills/loci` now links to that same canonical skill.
  Its installer also links canonical references when the skill file is linked.
- Codex registration supplies `LOCI_BASE_DIR=~/.codex/loci-index` and namespace
  `codex`, with no diagnostic override. A new process therefore selects normal.

Canonical guidance, reference docs, README and the repository-owned hook describe
retrieve/read. A whole-file redirect requires an isolated normal-service probe
to return an exact whole-file locator and successfully read its first page.
Broader or unsupported shell/read operations retain their existing fail-open
boundary. Global Claude state was not inspected or changed; only accessible
repository-owned compatibility and temporary installation fixtures were checked.

The user's pre-existing skill frontmatter edit is preserved separately. Product
and adapter provenance hashes at verification:

| File | SHA-256 |
| --- | --- |
| `src/loci/retrieval.py` | `6396c900713b44ffbbd9dfa186720a94594b36ad56375fc4746636acc679e13f` |
| `src/loci/mcp_server.py` | `67a5cc64c55493a101e60019b97d719fd635c7feccc67e2547be66306352b4e6` |
| `benchmarks/ordinary_adoption_normal.py` | `08f62064e006303bf1549b2063900b846b3eb6508d983a0140abedd5badcae4f` |
| Installed working `skills/loci/SKILL.md` | `edad48bc47cf62dfe8bacfe4f44014400b4faf6dff0a26911f8a8a0cb22cfe17` |
| `.shared/loci-mcp-wrapper.sh` | `4d849faa1e1e23bf65b627b68466754f51d89d0ce5db8752927366a0b92d0db7` |

## Verification

Focused acceptance passed: catalog concurrency/storage 85; normal adapter plus
frozen observer/review 49; legacy subprocess migration plus normal MCP 57;
TypeScript proof/replay plus normal retrieval 72; guidance/installation 15;
whole-file hook 20. These sets overlap and must not be summed. Public service
checks include decoys, ambiguous names, explicit endpoints, incoming/outgoing
edges, cycles, fan-out, large anchors and identifiers, source paging, unsupported
semantics, package-map controls and atomic output budgets. Real isolated stdio
checks exercise the two-tool catalog and exact source read.

The last full-suite run before the final empty-store correction returned
**2282 passed, seven failed**, with six deprecation warnings, in 202.09 seconds.
A diagnostic repeat returned the same counts in 202.98 seconds. The original
full output is `/tmp/loci-normal-final-pytest.log`; diagnostic repeat output is
in the session tool record. Six failures are baseline issues listed below.

The seventh exposed a new compatibility defect: an empty catalog read creates
the persistent zero-byte `.loci-repositories.lock`, so first MCP binding treated
an otherwise empty root as populated unowned data. A direct triggering sequence
reproduced the refusal with only that file present. Store initialization now
ignores only this named regular, empty, current-user-owned advisory lock without
group/other write permission. Symlinks, unsafe/nonempty locks, pending mutation
evidence and real data remain nonempty and fail closed as before.

The existing subprocess test now performs the triggering empty catalog read and
prints stderr on failure. Safe-lock and mutation/real-data refusal regressions,
store-identity tests and catalog tests pass **40/40** in 2.44 seconds after the
fix. The full suite was not rerun after that final focused correction. Compile
and diff checks pass. The full-run root had already been removed; attribution
uses the captured exact error and the deterministic independent reproduction,
not a retrospective listing of that removed root.

Six failures were independently reproduced on a clean detached `e8bb8fd` baseline
before the product changes, with `.manifest` excluded from that temporary tree:

| Test | Same baseline failure |
| --- | --- |
| `test_call_service.py::test_service_schema_seven_call_cache_forces_full_rebuild` | Expected graph schema 13; actual 14 |
| `test_service.py::test_graph_health_counts_imports_without_degrading_normal_unresolved_records` | Expected health counts omit five existing type-relation fields |
| `test_service.py::test_service_materializes_profile_without_leaking_declared_neighbors` | Same health-count expectation gap |
| `test_typescript_context_expansion_tools.py::test_relationship_normalization_preserves_actual_edge_identity` | Expected file owner; actual declaration owner |
| `test_multilingual_context_compare.py::test_validate_freeze_rejects_uncommitted_or_mismatched_controls` | Earlier environment-control mismatch than expected freeze-identity error |
| `test_typescript_context_three_arm_worker.py::test_worker_passes_pinned_engine_to_mcp_and_restores_compare_bindings` | Source differs from the historical pinned arm-C commit |

The baseline run returned six failures in 1.40 seconds using the repository
venv interpreter with `PYTHONPATH` set to the isolated baseline `src`. The
temporary worktree was removed. Its output is retained in the session tool
record, not a separate log file. These unrelated expectations and frozen
comparison artifacts were not rewritten to manufacture a green suite.

## Actual-host activation boundary and remaining work

The current Codex session's focused deferred discovery still finds **zero**
`loci_retrieve` or `loci_read` tools. It exposes the previously loaded legacy
catalog. Local fresh-server and standalone stdio tests prove implementation,
not activation in this host. No new actual-host retrieval or reserved adoption
run is claimed here.

Next is **W1.6.3**, after restarting Codex into a fresh session. The first resumed
operation must check the actual host's deferred normal tool discovery. It must
expose retrieve/read and no competing normal legacy routes. Then use that host
to retrieve context (for example, repo `/Users/brummerv/loci`, query
`retrieve_context`), follow a returned source reference, and retain the complete
native request/result and model-visible delivery. Reconcile those exact events
through the normal adapter, including result identity, source bytes, proof links
and costs. A source-free error or partial host capture cannot substitute for
validated graph delivery. Keep primary and fresh delegate provenance separate.

Complete W1.8.1 review and W1.8.2 selected-host acceptance with this evidence,
then freeze the installed runtime and adapter before W1.8.3's existing reserved
rows 15–24. Use the frozen prompts, roles, correctness rubric and denominators;
do not add graph reminders, replacement attempts or another campaign. W1.8.4
must report correctness, usage and cost separately, retaining failures and
unknowns. Other already-running selected hosts need their own restart. If an
expected tool is still absent, stop activation at that host boundary.

The original 14 observations, the ten reserved post rows, frozen observer/review
helpers and historical classifications remain unchanged. Baseline ordinary
behavior was four of eight runs discovering and invoking Loci, two delivering
relationships, and zero explicit `graph_*` calls. This supports a workflow
adoption gap; it does not establish universal non-use. The new default removes
the separate graph-choice step after Loci invocation. Whether agents invoke it,
receive useful proof and answer better remains the reserved experiment's question.
