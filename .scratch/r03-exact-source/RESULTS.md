# R0.3 exact-source architecture ablation

The decoupled candidate preserved exact source delivery and rejection behavior
on the fixed comparisons while substantially reducing Anvil read costs.
Recommendation: retain this source-access boundary as a viable candidate for a
separate integration decision. It remains experimental and has not been merged
into production. No agent campaign or model calls were performed.

## Identities and mechanism

- Unchanged control: `4cadfe1a233b9ec34b8ef25244d163d64297a8f4`.
- Candidate implementation: `a38e17d1456581786e950b892b2cd49684c08229`.
- Committed observer/harness: `be96a7f88332213d8a2473daa7992239f93aeaef`.
- Prospective scope and schedule: [protocol.md](protocol.md).

The candidate writes a narrow source-access projection only after ordinary
semantic validation. Its payload digest is anchored in the validated index;
the projection also binds the exact index bytes. Reads stream/hash the index
and verify that generation, then reuse the unchanged locator, containment,
live-source hashing, eligibility and UTF-8 pager. Missing, corrupt, incompatible
or mismatched projections fall back to ordinary reconstruction. Full repository,
coverage, resolver-control and active-extension path freshness checks and writer
locks remain in use.

This is **not graph-free**. Both arms retain full compilation, validation and
storage during indexing/refresh. Each ordinary candidate read still streams
the approximately 73.7 MB Anvil index twice (freshness and delivery). No graph
enrichment setting changed. The integrity root is the existing trusted local
index; this is not authentication against an attacker rewriting that root.

## Capability and isolation

All six pairs passed: three fixed comparisons, two fresh repetitions each,
alternating arm order. Twelve separate stores/namespaces and disposable
implementation checkouts were used. Fixtures were independently hash-verified
before and after each process. Both primary repositories retained their HEAD,
staged diff, dirty/untracked inventory and file bytes. All twelve owned runtime
directories and execution worktrees were removed; implementation worktrees and
retained results remain. See [validation.json](validation.json) and
[preservation-after.json](preservation-after.json).

| Comparison | Independent result |
| --- | --- |
| Maintained Anvil snapshot: `src/brain-context/render.ts` | Exact 13,067 bytes, two pages; first/repeat/no-refresh and continuation output equivalent across arms. |
| Small Unicode + Go/Cargo/JS controls | Exact Unicode pagination and readable `go.mod`, `Cargo.toml`, `jsconfig.json`; all output and accounting fields equivalent. |
| Small rejection probes | Both arms reject all nine probes: foreign, invalid extent/hash, unindexed, malformed, UTF-8 boundary, stale, stale with refresh, outside symlink. Codes, messages and details agree after isolated-root normalization. |

In total: 24 source-request executions, 84 successful page calls including
repeats/diagnostics, and 36 expected rejection calls. The independent observer
checks frozen bytes, hashes, contiguous extents, line numbers, UTF-8, page
completion and output-size limits/accounting. Only root-bound opaque handles
and repository paths in error details are normalized for comparison.

Independent retained replay passed for all 24 request executions without the
original stores/worktrees. Separate copied-evidence controls rejected corrupted
packets, changed source bytes (including same-length corruption with unchanged
spans/hash/accounting), missing continuation pages and missing UTF-8 probes.
Focused source tests also caught an initial sidecar forgery that could add an
unindexed file; the root-index anchor correction and regression test are in the
measured candidate. Missing/altered anchors, corruption, legacy fallback,
version gates, freshness locks and active-path containment are tested.

The five semantic proof-support discrepancies remain **unresolved**: one in
`anvil_temporal_arguments`, two in `anvil_retrieval_limits`, two in
`python_loci_bundle_contract`. Their exact violations, original identities and
artifact hashes are retained in [unresolved-semantic-proofs.json](unresolved-semantic-proofs.json).
The original full retrieval result stays invalid. Its strict scorer is unchanged;
exact-source success supplies no semantic proof or agent-task correctness credit.

## Resource results

Means of two fresh repetitions; raw values, setup costs and work counts are in
[summary.json](summary.json) and the three raw result directories. First-read
means process-cold against a preindexed store; OS caches were not flushed.
First, repeat and continuation reads all include `ensure_fresh=True`.

| Anvil measurement | Control | Candidate |
| --- | ---: | ---: |
| First read | 3,525 ms | 126 ms |
| Repeated first page | 3,506 ms | 105 ms |
| Continuation read | 3,552 ms | 124 ms |
| No-refresh diagnostic | 1,796 ms | 31.6 ms |
| Reader CPU, full four-call sequence + setup | 12.53 s | 0.554 s |
| Reader process peak RSS | 426.8 MB | 55.8 MB |
| Initial indexing | 5.019 s | 5.080 s |
| Indexing process peak RSS | 497.1 MB | 498.1 MB |
| Index + first + repeat + continuation operations | 15.602 s | 5.436 s |
| Index/read process elapsed total, including diagnostic, imports and archival | 18.516 s | 6.574 s |
| Retained working store size | 75,670,509 B | 75,689,850 B |

On stable Anvil reads, baseline observes four graph-context loads and seven
semantic validations per reader sequence; candidate observes zero of each.
Both perform three freshness checks and no refresh. Indexing work matches:
163 indexed files, 2,284 symbols, 18,441 calls, 11,102 references, 2,991 type
relations and 4,532 graph edges. Full graph indexing memory is unchanged; the
approximately 19 KB projection increases storage slightly. Do not describe the
reader RSS reduction as an indexing or whole-system peak-memory reduction.

Small-control first-read totals (four files per process) were 55.6 vs 38.2 ms,
repeat totals 41.1 vs 29.2 ms, and index + first + repeat + continuation totals
191 vs 169 ms. Reader peaks were 51.9 vs 51.4 MB; process totals 662 vs 649 ms.
Small indexing was 65 vs 76 ms. These small absolute differences are noisy and
startup dominates. Mutation probes perform two full reindexes in both arms;
candidate reader still observes full validation there. Their refresh/restoration
costs and slightly higher candidate RSS remain charged in the raw results.

These are descriptive fixed-fixture measurements, not statistical or population
claims. No Swift-specific live fixture, concurrent writer stress campaign,
relationship-proof fix, graph-free redesign or agent benefit is established.
The shared freshness scanner still scans the repository and the index still
scales with graph size. Legacy stores retain legacy costs until normal indexing
writes a valid projection.

## Validation and reproduction

Candidate checks: **296 passed, 2 deselected**. The two graph-health dictionary
expectation failures were independently reproduced on unchanged control; they
were not repaired. Existing harness/corpus plus source projection checks:
**26 passed**. Direct-read harness checks: **3 passed**. The latter totals overlap
the source tests, so they are separate commands, not a summed unique-test count.
Exact commands and replay receipts are in [validation.json](validation.json).

Using the prepared repository Python, run at the recorded observer revision or
this evidence-only descendant:

```sh
python -B -m benchmarks.architecture verify --output .scratch/r03-exact-source/results/anvil
python -B -m benchmarks.architecture verify --output .scratch/r03-exact-source/results/small-controls
python -B -m benchmarks.architecture verify --output .scratch/r03-exact-source/results/small-negatives
```

For a new measurement, use a new output path and the command in
[benchmarks/ARCHITECTURE.md](../../benchmarks/ARCHITECTURE.md#exact-source-comparisons),
the two implementation refs above, the explicit mechanism string, and two
repetitions. Build the small corpus with
`architecture_reads.build_small_suite(Path(NEW_INPUT_DIRECTORY))` or reuse the
retained [small input](inputs/small/corpus.json). Run four `--read-file` values
for `imported_interface:unicode.md`, `go.mod`, `Cargo.toml`, `jsconfig.json`;
then a separate Unicode-only comparison with `--read-negatives`.
Use `PYTHONPATH=src` when running tests against a worktree to avoid importing
the primary checkout's editable package. Each result retains exact evaluator
sources and a hashed artifact manifest; the manifest hashes are pinned again
in summary.json. No production branch was modified.
