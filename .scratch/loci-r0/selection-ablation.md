# R0 anchor selection ablation — 2026-10-22

**Decision: NO-GO for literal-first with metadata fallback as a general selection policy.** It repairs the reproduced mixed literal query, but it scans source on ordinary metadata queries, admits incidental references as anchors, and can displace the named declaration from the three-anchor set. The small fixture's graph traversal recovered that declaration as a related item; this is an anchor-precision regression, not a demonstrated complete-source miss. The experiment removes no component or maintenance obligation.

## Scope and hypothesis

The original `_select_anchors` checks explicit seeds and exact files first, then returns as soon as `select_graph_anchors` finds metadata candidates. `_literal_anchors` is never tried on that path. The ablation moves the existing bounded literal scan ahead of metadata, returning metadata only when it finds no literal. Explicit seeds and exact files remain ahead of both. No graph, packer, limit, or output contract was changed.

The strongest predicted benefit was direct coverage for mixed queries containing an exact source phrase that weak symbol metadata suppresses. The predicted costs were full-corpus lookup on ordinary queries and literal occurrences in references/comments taking anchor capacity before the named declaration. Proof was a matched, deterministic fixture, output/lookup accounting, focused existing tests, and a reviewable one-function diff. This fixture is **diagnostic**, assembled from the historical `connection reset §42§` symptom and existing retrieval-test patterns; it is not an independent task corpus.

## Isolation and pins

- Primary checkout `/Users/brummerv/phluxxed/loci` was already dirty with separate R0.1 work. No production source was edited there.
- Experimental detached worktree: `/Users/brummerv/phluxxed/loci/.worktrees/r0-selection`, baseline `f41b3eaa4c7871c68972de5f760572a6bcbe1760`, initially clean. Control `src/loci/retrieval.py` SHA-256 `b971f6821921af309d0a101ec1b18e50059a91cb1b46110327e67924d34af5b7`; candidate SHA-256 `e5342ecd36e84cd4e708f8065cb45facd9fa83b59d6475433520f863d1b0ba63`.
- Python 3.14.5 from the primary checkout's existing `.venv`, with `PYTHONPATH` inserted to the experimental worktree `src`. Each condition freshly indexed the same six files (12 symbols, 8 graph edges, complete fixture coverage) into its own `LOCI_BASE_DIR` under the worktree. No global Loci catalog was used. Full per-file content hashes, environment and complete packets are in the raw JSON.
- The first six-case control and candidate runs preceded the added `ordinary_type` case. Their common results exactly matched the later seven-case runs, including complete result packets. The same fixture content hashes were recorded in all runs.

## Matched result

The target is the source declaration or phrase-containing function named by each diagnostic case. `anchor` is direct selection; `item` includes graph-enriched related source. Counts and bytes are from the returned packet. Times are one local wall/CPU sample per case, in milliseconds, so they indicate fixture cost only and are not a throughput estimate.

| Case | Control anchor / item | Literal-first anchor / item | Lookup files / bytes, control → candidate | Output bytes, control → candidate | Wall ms, control → candidate |
| --- | --- | --- | ---: | ---: | ---: |
| `mixed_collision`: `connection reset §42§` | wrong `connection` / target absent | `execute` / target present | 0 / 0 → 6 / 548 | 2387 → 2276 | 7.49 → 4.95 |
| `literal_only`: `§42§` | `execute` / present | `execute` / present | 6 / 548 → 6 / 548 | 2276 → 2276 | 4.36 → 3.96 |
| `ordinary_symbol`: `assembleEnvelope` | declaration / present | declaration + two `entry.ts` references / present | 0 / 0 → 6 / 548 | 10493 → 10504 | 8.56 → 10.15 |
| `ordinary_type`: `WireEnvelope` | declaration / present | three `assemble.ts` occurrences; declaration omitted from anchors / present as related | 0 / 0 → 6 / 548 | 10519 → 9978 | 7.68 → 7.57 |
| `ordinary_words`: `assemble envelope` | declaration / present | metadata fallback declaration / present | 0 / 0 → 6 / 548 | 10569 → 10571 | 8.26 → 8.72 |
| `exact_file`: `semantic/assemble.ts` | file / present | file / present | 0 / 0 → 0 / 0 | 9652 → 9652 | 7.65 → 7.34 |
| `explicit_seed`: `execute` seed with mixed query | `execute` / present | `execute` / present | 0 / 0 → 0 / 0 | 2257 → 2257 | 3.65 → 2.41 |

The candidate's `ordinary_type` packet reports `anchor_limit: 1` and `ambiguous_anchor: 3`; the metadata-first packet has no anchor ambiguity there. The `ordinary_symbol` candidate reports `ambiguous_anchor: 2` where the control has none. `ordinary_words` keeps the same metadata anchor but still performs the full scan. Exact-file and explicit-seed result packets are identical across conditions. The seven-case CPU measurements are in the raw JSON; full retrieval includes graph packing, so wall/CPU differences should not be read as isolated selection timing. The 6-file lookup was 548 bytes; the production scan is bounded by existing limits of 4096 files and 32 MiB, which were not approached here.

## Verification and limits

- Before modification, focused `tests/test_retrieval.py` subset: 5 passed. After modification, the same subset: 5 passed; entire `tests/test_retrieval.py`: 18 passed. `git diff --check` passed.
- Seven fixed requests used the same fixture content and indexing procedure for control and candidate. The first six repeated result packets exactly across independent fresh-store runs. Full packets expose anchors, omissions, direct/related items, lookup work, output bytes, and graph proof.
- The extra mixed and ordinary-type fixtures are diagnostic, not independent evidence that the policy improves or worsens real agent answer correctness. The graph recovered the displaced type source in this tiny fixture. No live agent evaluation, production-corpus timing, large-index limit test, or integration was performed.

## Artifacts and rerun

- Driver: [`selection-driver.py`](selection-driver.py); complete final control and candidate packets: [`selection-control-typecase.json`](selection-control-typecase.json), [`selection-literal-first-typecase.json`](selection-literal-first-typecase.json). Initial six-case packets: [`selection-control.json`](selection-control.json), [`selection-literal-first.json`](selection-literal-first.json).
- Reviewable worktree change: [`selection-diff.patch`](selection-diff.patch), or `git -C /Users/brummerv/phluxxed/loci/.worktrees/r0-selection diff -- src/loci/retrieval.py`. The candidate is left only in that detached experimental worktree.
- Commands used (the driver refuses an existing store directory, so choose fresh `--run-id` values on rerun):

```sh
/Users/brummerv/phluxxed/loci/.venv/bin/python /Users/brummerv/phluxxed/loci/.scratch/loci-r0/selection-driver.py --worktree /Users/brummerv/phluxxed/loci/.worktrees/r0-selection --variant control --run-id typecase --output /Users/brummerv/phluxxed/loci/.scratch/loci-r0/selection-control-typecase.json
/Users/brummerv/phluxxed/loci/.venv/bin/python /Users/brummerv/phluxxed/loci/.scratch/loci-r0/selection-driver.py --worktree /Users/brummerv/phluxxed/loci/.worktrees/r0-selection --variant literal_first --run-id typecase --output /Users/brummerv/phluxxed/loci/.scratch/loci-r0/selection-literal-first-typecase.json
/Users/brummerv/phluxxed/loci/.venv/bin/python -m pytest -q tests/test_retrieval.py
```

The control command was run while the worktree file contained the pinned baseline source; the candidate source was restored immediately afterward. A rerun needs the same source switch, not just a new store ID.
