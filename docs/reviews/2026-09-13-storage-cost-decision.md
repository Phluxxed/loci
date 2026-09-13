# W3.3 — storage-cost decision

Decision: **defer storage/indexing changes; no change now**.

Task `task_f97e457ebc125c47ba7076bf7b05f286`, canonical Objective
`obj_0110c8712b21bdd2c12532f189d84a74` at `/Users/brummerv/loci`.
The retained evidence establishes no material storage bottleneck. This is not
a claim that the current storage design scales to every repository.

## Measured evidence and attribution

Reviewed current Manifest criteria, the retained W4.7 protocol/outcomes,
historical graph/indexing measurements and relevant source at isolated commit
`86bca31305defdeabd2b5d1fef247a64ddc4eec5`. An independent audit checked W4.7
fields and budget failures. Reductions below read the frozen files; no new
profiling, provider run, benchmark, rescore or implementation was performed.

The [W4.7 results](https://github.com/Phluxxed/loci/tree/86bca31305defdeabd2b5d1fef247a64ddc4eec5/benchmarks/results/multilingual-context-workflow-v1)
retain 114 attempts, each under `<case>-r<1..3>-<A|B>`. Across their `result.json`
files, `baseline.adapter_elapsed_ms` has median **41.877 ms A / 50.715 ms B**
and maximum **135.825 ms**. This is aggregate adapter work per attempt, not
storage-only time or a per-call percentile. `report-summary.json` records
end-to-end p95 **107.322 s A / 122.186 s B**; that time includes work beyond Loci.

All 114 `provenance.json` files contain `index_seconds`: total fresh fixture
indexing ranges **0.009052–0.074547 s**, median **0.019788 s**. These small
snapshots do not establish performance on a full maintained repository. Fresh
indexing is separate from the task tool-adapter timing and is not a measurement
of incremental indexing, writes alone or graph-loading cost.

| Cost category | Available evidence | What remains unknown |
| --- | --- | --- |
| Loading | `IndexStore.load` reads/deserializes the full JSON index; `get_graph_state` loads then validates graph state. W4.7 records whole-operation `adapter-trace.json.events[].elapsed_ms` and aggregate adapter time. | JSON read, decode and validation durations; cache warmth, repeated-load contribution and large-repository loading cost. |
| Adjacency | `graph_adjacency` sorts edges, allocates steps, and returns sorted adjacency tuples. Explore usage records bounded examined/selected counts and limits. Historical graph-call timing includes adjacency work. | Adjacency build/lookup time, allocation volume and its share of latency. Traversal caps are not a bound on total resident index size. |
| Serialization | Trace `serialized_bytes`, `source_bytes`, `response_json` and result output accounting describe delivered bytes. The complete output totals remain unavailable for 63 graph-accounting-incomplete rows. Index writes serialize full JSON. | Serialization CPU time, persistent encoding costs and whether either is material. Output bytes are not disk bytes or time. Null complete totals must not be replaced by trace subtotals. |
| Incremental indexing | Current code reuses unchanged extraction records, then materializes graph state and writes when indexing executes. `ensure_fresh_index` can return without indexing/writing when fresh. W4.7 uses fresh indexes, not no-change/incremental workloads. Historical Stage 6 records a no-change run. | Current changed-file and no-change indexing costs, graph rebuild share and maintained-repository regression. Extraction reuse does not imply a delta-only disk update. |
| Memory | Source shows full JSON structures and adjacency allocation. The inspected retained protocol/result/trace/provenance fields contain no RSS, heap or allocation measurement. | Peak/resident memory, GC/allocator and page-cache effects; no measured memory-budget breach is established. |
| Writes | `IndexStore.write` validates graph data, copies each indexed source file once into a replacement mirror, writes full `index.json` through temp-file replacement and updates the catalog. Fresh-index time includes this work. | Write count/volume/time, write amplification and durability costs. Provider `cache_write_input_tokens` measures prompt caching, not Loci disk writes. |

Source anchors:
[`IndexStore.write/load/get_graph_state`](https://github.com/Phluxxed/loci/blob/86bca31305defdeabd2b5d1fef247a64ddc4eec5/src/loci/storage/index_store.py#L252),
[`graph_adjacency`](https://github.com/Phluxxed/loci/blob/86bca31305defdeabd2b5d1fef247a64ddc4eec5/src/loci/graph/traversal.py#L152),
[incremental extraction reuse](https://github.com/Phluxxed/loci/blob/86bca31305defdeabd2b5d1fef247a64ddc4eec5/src/loci/service.py#L260),
[graph materialization/write](https://github.com/Phluxxed/loci/blob/86bca31305defdeabd2b5d1fef247a64ddc4eec5/src/loci/service.py#L429)
and [fresh-read guard](https://github.com/Phluxxed/loci/blob/86bca31305defdeabd2b5d1fef247a64ddc4eec5/src/loci/service.py#L519).

## Budgets and historical context

The [frozen protocol](https://github.com/Phluxxed/loci/blob/86bca31305defdeabd2b5d1fef247a64ddc4eec5/benchmarks/comparisons/multilingual-context-workflow-v1/protocol.md)
sets 10 s per operation and 180 s per task; explore permits 8 KiB evidence,
16 KiB output, five anchors, three hops, 64 nodes, 12 items and 32 neighbors.
Other retrievals permit 16 KiB source, 32 KiB output and 64 spans; tasks permit
128 KiB source, 256 KiB output and 24 calls. These are retrieval/workflow bounds,
not allocated memory or disk-write budgets.

The retained failures include eight input-token breaches, two evidence-span
breaches and one task timeout, with overlap between categories. None identifies
a storage phase as the cause. The timeout
`javascript_unproven_dependencies-r2-A` records about 96 ms aggregate adapter
work against 180 s task time. It does not demonstrate a storage timeout.
Graph-name reconciliation, hidden pagination/seed bounds and exact Go/Cargo
control access remain the separately recorded W5 issues.

Older evidence supplies context, not a current storage acceptance result:

- [Stage 3](https://github.com/Phluxxed/loci/blob/86bca31305defdeabd2b5d1fef247a64ddc4eec5/docs/plans/2026-07-13-extensible-graph-retrieval-stage-3.md#L614)
  records 61.29 ms mean whole anchor-call latency.
- [Stage 4](https://github.com/Phluxxed/loci/blob/86bca31305defdeabd2b5d1fef247a64ddc4eec5/docs/plans/2026-07-13-extensible-graph-retrieval-stage-4.md#L887)
  records 114.380 ms mean whole traversal-call latency with configured budgets
  satisfied. Its setup occurs outside the timer; it does not isolate adjacency
  or storage and is not a cold-start/end-to-end measurement.
- [Stage 6](https://github.com/Phluxxed/loci/blob/86bca31305defdeabd2b5d1fef247a64ddc4eec5/docs/reviews/2026-07-15-extensible-graph-retrieval-stage-6-final-review.md#L220)
  records 1.299 s full and 1.156 s no-change indexing for 1,116 symbols/611 edges.
  A five-run implementation comparison increased median indexing by 0.080 s
  (6.7%). These July whole-operation observations do not attribute disk, parser,
  resolver, memory or graph phases and do not certify September performance.

## Decision and reopening condition

The strongest reason to investigate later is the visible full-index load and
rewrite work: it could become expensive as a repository grows. B's roughly
8.8 ms higher median adapter time also deserves an honest record, but its
different operations and evidence cannot establish a storage regression.
Neither observation identifies a material bottleneck or supports choosing a
database, query language, ranking algorithm or embedding system now.

Reopen when a relevant workload shows a user-visible latency, memory or write
cost and evidence attributes a material share to loading, adjacency,
serialization or indexing/storage. Record workload size, freshness/change
pattern and the relevant budget. Only then choose the smallest justified
adjustment with scoped performance and compatibility acceptance, preserving
source provenance, freshness, uncertainty and evidence budgets. Missing
attribution alone does not schedule a profiling campaign.

W3.3's review and no-change criteria are satisfied; its change-only design
criterion is inapplicable. Acceptance is the retained-field reduction and
source audit, Manifest criterion/reference readback and scoped diff checks.
W1/W2/W4, both earlier W3 decisions and W5 remain unchanged.

Next: **W3.4 — concrete cross-repository use-case decision**,
`task_c9ec6f8dab01945a485822c1f4719800`; it is not started by this record.
