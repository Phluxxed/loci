# R0 repeated graph-validation ablation — 2026-10-22

The full freshness-enabled Anvil exact read reconstructs and validates the whole graph twice, loads its 73.75 MB index JSON three times, and scans/hashes the repository once. A content-keyed, defensive-copy cache preserves the tested packets and rejection behavior but improves median read wall time only 9.0% (3,718 → 3,383 ms); retrieve improves 1.0%. This implementation does not justify a production cache redesign. Repeated graph loading is a demonstrated cost; the replacement's complexity/value tradeoff remains questionable.

## Control, intervention and isolation

Baseline `f41b3eaa4c7871c68972de5f760572a6bcbe1760`. Dedicated detached worktree `.worktrees/r0-validation`; production source unchanged. Existing Python3.14.5 environment, explicit `PYTHONPATH=src:.`, `LOCI_BASE_DIR` and namespace under that worktree. The [driver](validation-driver.py) records source module, platform and interpreter and uses existing SHA-verified corpus materialization. The frozen TypeScript v3 `imported_interface` and maintained `anvil` source snapshots are inputs, not a rerun or rescore of historical agent trials. Anvil has187 archived files;163 eligible source files produce2,284 symbols and4,532 edges. Full source hashes remain in the isolated input/index and immutable corpus inventory.

The sole intervention wraps `IndexStore.validate_graph_state`: key every input it reads (`symbols`, `file_hashes`, `graph`) by canonical JSON SHA-256; retain one privately copied validated state; deep-copy on a hit. Misses run the original validator. Full JSON loading, store construction, freshness scan, control hashing, contained live source reads, stale references, proof assembly and pagination remain active. The copy prevents caller mutation of cached input hashes. A graph cache shared across changing inputs, processes or concurrent writers is not designed or accepted here.

Control precedes candidate. First calls are recorded separately; three warm repetitions per operation alternate arm order. These reuse the existing corpus repetition count; no new agent budgets or output limits exist. Both arms use the same repository, source refs and request. Exact complete packet equality is asserted, including omissions, usage, source/proof and page continuation. Existing tests and negative checks validate the chosen replacement, not its architectural usefulness.

## Results

Wall medians and CPU medians in milliseconds; descriptive local observations, not a throughput or population estimate. The active corpus worker ran elsewhere during portions of these samples, so small deltas cannot establish a stable efficiency gain.

| Input / operation | Control wall | Cache wall | Wall saved | CPU control → cache | Packet |
| --- | ---: | ---: | ---: | ---: | --- |
| imported_interface / retrieve | 7.61 | 7.65 | -0.6% | 5.23 → 4.67 | identical |
| imported_interface / read | 5.03 | 4.57 | 9.2% | 3.11 → 2.76 | identical |
| anvil / retrieve | 4075.09 | 4035.98 | 1.0% | 4037.87 → 3997.81 | identical |
| anvil / read | 3718.17 | 3382.63 | 9.0% | 3677.01 → 3356.80 | identical |

The small fixture does not show a retrieve wall benefit. Both Anvil arms still decode full index JSON and candidate hits serialize/hash roughly49.5 MB of validation input and deep-copy the full typed state on each validation request; two such requests per operation charge99.05 MB of cache-key encoding. No backing data, semantic extraction or graph persistence is eliminated. Cache memory and peak resident memory were not separately measured.

[Raw results](validation/results.json) preserve every first call, repetition, wall/CPU time, operation count, packet hash, index/setup cost and negative result. [Anvil read profile](validation/anvil-read-profile.txt) is a separate instrumented control:9.27s cumulative including8.54s in two graph validation calls, of which7.37s is `GraphIndexState.from_dict` reconstruction and1.17s record/edge validation. Profiling overhead is material: compare attribution, not those seconds to unprofiled samples. The graph object conversion is the larger part of the measured validation path. [Raw cProfile](validation/anvil-read.prof) is retained.

Fresh Anvil indexing took4,270 ms; explicit no-change incremental indexing3,919 ms (91.8% of cold). This is one observation each, not an indexing ablation. The unchanged path reuses parses but still resolves, validates, mirrors and persists the full graph. The index JSON is73,747,104 bytes versus1,910,473 source-mirror bytes (~38.6×); this excludes catalog/source-ref files. It demonstrates representation expansion for this source, not proof that every stored field is unnecessary. Small fixture cold/no-change observations are37.66/10.74ms.

## Verification, disposition and limits

- Control and cache emitted identical full retrieve/read packets for both inputs. Representative packet JSON, source hashes and continuation fields are retained under [validation/](validation/).
- Duplicate graph endpoints and invalid graph schema remain rejected with matching `INVALID_GRAPH_SCHEMA`; actual live source drift remains `SOURCE_STALE`; mutation of a returned state cannot change the private cached state. Four checks pass on both snapshots.
- [Focused candidate tests](validation-tests.txt):67 passed, same retrieval, enrichment, source-expansion, normal-acceptance and source-reference suite as [control](control-tests.txt). No broader integration claim.
- No model ran. Output equality implies identical delivered information in these requests, not equivalent internal model reasoning or terminal task completion. Provider tokens/retries/costs and peak memory remain unmeasured. No sandbox/configuration changes.

Disposition: **INCONCLUSIVE for adopting this cache**. Two integrity checks over identical validation inputs perform duplicate work, but defensive copying and cache-key construction displace much of its cost. First-operation overhead, concurrency, cache invalidation across writers and large-index memory would need their own contract before adoption. This closes the tested hypothesis; it does not trigger another cache tuning pass. A more consequential next experiment is a direct source-read boundary that does not reconstruct semantic records while preserving source/control authorization and drift checks.

Rerun from a fresh disposable copy (driver intentionally rejects existing materialized snapshots):

```sh
cd /Users/brummerv/phluxxed/loci/.worktrees/r0-validation
PYTHONPATH=src:. /Users/brummerv/phluxxed/loci/.venv/bin/python r0_validation.py
```
