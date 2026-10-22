# R0.4: graph-free architecture ablation

The graph-free candidate retained trustworthy file discovery, lexical search,
exact source reads and follow-up acquisition at much lower fixed-suite resource
cost. It did not preserve semantic relationship proofs or all bounded source
acquisition. The evidence supports a separate demand-driven semantic experiment;
it does not support production removal of the graph or Loci V2 implementation.
No production integration or model evaluation campaign was performed.

## Scope and mechanism

All work is retained in the disposable `experiment/r04-graph-free` worktree.
Implementation `ae4c0e8` adds one file-only acquisition module; production service,
resolvers, graph schemas, launchers and main branches are unchanged. Original
Loci is `4cadfe1`, whose `src/` bytes match the historical `8b21db8` reference.
Graph-enabled R0.3 is `b75fe58`. That reference keeps eager graph indexing and
storage while decoupling exact source delivery from semantic reconstruction.

The candidate stores only relative file hashes, repository identity, omissions
and a generation digest. It uses current file discovery and source literal/token
search; no AST, symbol table, relationship index, semantic resolver, stored edges,
or graph reconstruction runs. References locate whole files and current hash-
checked offsets. Search refreshes the inventory; reads recheck eligibility and
current bytes. Files are opened through contained, nonsymlink components;
nonregular/binary/non-UTF8 files are refused. Git ignore policy, cross-repository
references, stale/deleted/excluded source, UTF8 pagination and complete-envelope
byte accounting have focused checks.

This is an experiment module exercised by the retained harness, not a new MCP
surface or production service migration. Its bounded text search deliberately
has no semantic graph-ID contract, resolver-control interpretation, ambiguity
resolution, call/type/import proof, reverse dependency analysis, or impact claim.
Its inventory knows text manifests as source, not their semantic effect.

## Acquisition and proof measurement

The [prospective protocol](protocol.md) froze the unchanged 17-case TypeScript v3
and 19-case multilingual v1 corpora, two repetitions in alternating arm order,
and a shared acquisition policy before scored execution. Every case starts with
the existing authored entry query. The scheduler sees only delivered source and
filename/hash/size inventory. It expands incompletely delivered files, discovers
lexically mentioned paths and ancestor manifests, then observed identifiers.
It never sees expected context spans, relationships, missing scores or gold answers.
No policy or candidate tuning followed the measured misses.

Each case allows five retrieval calls and sixteen continuation calls, with soft
admission limits of 128 KiB source and 256 KiB source-tool response bytes; inventory
is charged separately. Full final responses are preserved and charged, including
overshoot. Incomplete selected extents are hydrated in returned order until the
limits stop acquisition. The inventory is an explicit benchmark discovery adapter
for all arms, rather than a claim about unchanged normal graph MCP capabilities.

Source coverage independently requires every byte of the authored interval,
allowing adjacent delivered fragments. Entry coverage is measured by source
span, independently of graph IDs. Semantic scoring remains separate: the frozen
strict TypeScript/multilingual scorers are unchanged, including their existing
TypeScript generic-dependency qualification. Zero graph-free claims earn zero
positive semantic credit; absence of forbidden claims is vacuous for that arm.
No task answers were generated or graded.

## Five proof discrepancies

The [per-edge audit](proof-audit.md) and [machine-readable evidence](proof-audit.json)
reconstruct all five persisted resolved call records, hashes and required support
intervals. Normal retrieval deliberately replaces full caller-definition support
with an exact call site. The old architecture adapter tags normal packets with
exploration intent, causing the strict scorers to inspect only each relation's
linked sources. Those linked sources lack the whole caller interval in five
claims across `anvil_temporal_arguments`, `anvil_retrieval_limits`, and
`python_loci_bundle_contract`. The original packet score and historical invalid
result remain unchanged. This is not evidence of five false call targets.

The same retained sessions actually deliver every missing caller definition,
through continuations and, for one Python edge, another source in the initial
packet. A **distinct session-proof measure** remaps only validated, actually
acquired same-case sources with retained packet provenance and runs the unchanged
strict scorers against the original claimed edges. It fetches no extra source,
adds no edge, and still requires all persisted support/control intervals. It does
not relabel packet-linked proof as complete or establish that an agent used it.
Negative controls remove the caller's final byte from *all* delivered coverage
for each of the five edges, keeping the original index and claims: strict
session proof fails. Source corruption also fails. This resolves their impact
on session-acquisition comparison validity without weakening the scorer. Expanded
follow-ups expose three additional packet-linked proof deficits in the same
Python case (`_append_bundle` → `_relation_key`, `pack_exploration` → nested `omit`,
and `pack_exploration` → `_base`). They remain explicit failures in the frozen
packet score. All acquired session support still satisfies the unchanged strict
scorer; there are zero session proof violations. No incomplete packet claim is
counted as complete packet proof.

## Capabilities and source misses

For R0.3 versus graph-free, both repetitions delivered identical capabilities:

| Dimension, 36 cases | R0.3 graph | Graph-free |
| --- | ---: | ---: |
| Entry source acquired | 36/36 | 36/36 |
| Authored spans after initial query + hydration | 162/187 | 118/187 |
| Authored spans after bounded follow-up | 186/187 | 180/187 |
| Cases with every authored span | 35/36 | 34/36 |
| Strict session semantic links delivered | 78/84 | 0/84 |

The graph-free candidate misses five `retrieve.ts` spans in
`anvil_retrieval_limits`, and the reexport/module spans in `core/src/lib.rs` in
`rust_contained_optional_reexport`. It acquires the private-source span in
`rust_unproven_contracts` that the graph arm misses. The first is a substantial
repository case: graph traversal surfaces reverse callers and their implementation;
the lexical arm's bounded top-three hits and follow-ups spend space on other
matching files and manifests. Its final Anvil task delivers more unique source
(114,951 B versus 83,147 B) while still missing the five target spans. Graph
selection therefore supplies useful targeting under this policy and budget.

The Rust deficit is on a 513-byte fixture: the candidate's five queries consume
manifest and API discovery before reaching the reexport module. This is a
bounded acquisition-policy failure, not proof that semantic analysis is necessary
to obtain that file. The graph-free arm's extra private source likewise establishes
text availability, not visibility, admissible binding, or a proven relationship.

The graph retains pre-resolved call/type/import bindings, declared/possible
configuration and uncertainty distinctions that plain source search does not
produce. A file-only arm must leave these questions unproved. The deterministic
evaluation demonstrates extra source targeting and supported relation evidence,
not that every graph result is necessary or that no simpler strategy can recover
it. R0.3 itself delivers only 78 of 84 required semantic dependencies.

Thirty-two cases use snapshots smaller than 1 KiB. Both arms deliver about 97%
of those snapshots on average; 23/32 are delivered in full. High span coverage
there frequently means reading almost the whole fixture. The retained per-case fraction of
snapshot delivered exposes this. The Anvil snapshot is 2,442,185 B across 187
frozen files; the Loci Python case is one 17,942-byte file. Neither the small
fixtures nor these two source snapshots establish population-wide scalability,
repository diversity, or realistic agent-task completion.

## Resource comparison

Means of two fresh repetitions over the complete fixed suite. Original and R0.3
have identical source/proof outcomes (186/187 spans, 78/84 session semantic links).
R0.3 was measured in both pairs; all four R0.3 executions agree on capabilities
and delivered bytes. The main table uses its pair with graph-free; the second
pair is retained separately in [summary.json](summary.json).

| Whole fixed workload | Original Loci | R0.3 graph | Graph-free |
| --- | ---: | ---: | ---: |
| Initial indexing, 31 snapshots | 5.54 s | 5.50 s | 1.07 s |
| Initial retrievals + follow-ups | 64.21 s | 62.80 s | 7.06 s |
| Continuation reads | 146.81 s | 4.18 s | 1.53 s |
| All worker elapsed, including imports/archival | 218.19 s | 74.03 s | 10.12 s |
| Worker CPU including child processes | 214.43 s | 71.49 s | 6.26 s |
| Fixture/worktree setup elapsed | 2.68 s | 2.52 s | 2.75 s |
| Workers + fixture/worktree setup elapsed | 220.87 s | 76.55 s | 12.87 s |
| Workers + setup CPU | 216.49 s | 73.54 s | 8.46 s |
| Peak worker RSS, mean per-repetition peak | 595.0 MB | 596.5 MB | 39.8 MB |
| Retained working store | 77.64 MB | 77.70 MB | 35.9 KB |
| Delivered source bytes, including repeats | 459,848 B | 459,848 B | 336,926 B |
| Repeated source bytes | 181,096 B | 181,096 B | 89,206 B |
| Total delivered context, including inventory/framing | 1,951,173 B | 1,951,173 B | 933,635 B |

Decimal MB/KB. Exact repetitions, phase CPU/work counts, per-case context and
fractions are in [summary.json](summary.json), generated directly from immutable
result files by [summarize.py](summarize.py). Source-tool call counts are 36 initial
retrievals + 140 follow-ups + 57 continuations for each graph architecture,
versus 36 + 143 + 47 for graph-free. Follow-ups stop early only through the frozen
admission/exhaustion rules. Three graph-free extra search calls are charged.
All working-cache receipts are zero bytes. Source/dependency checkouts and the
shared interpreter are retained as common experimental infrastructure; store
numbers are derived runtime data, not the installation footprint of a deleted
production package.

R0.3 preserves acquisition while avoiding roughly 143 seconds of continuation
reconstruction here. It does not lower whole-worker peak memory or eager graph
storage. Removing semantic work cuts another substantial cost, but the source
and semantic losses above prevent treating that as an equivalent replacement.

All costs include eager initial indexing once per snapshot (31 snapshots per
36-case suite), current-source/freshness work inside subsequent calls, imports,
source continuation and archival in fresh isolated workers. Three Anvil cases
share one index within each suite. CPU includes worker children such as Git.
Peak RSS is a process lifetime high-water mark, not a separately sampled index
or read peak and not a simultaneous multiprocess memory sum. Working store
bytes include derived source-reference state. Fixture export/worktree setup is
reported separately; independent evaluator/replay time is not product retrieval
cost. OS caches were not flushed. Two repetitions are descriptive observations,
not confidence intervals or a population performance claim.

The graph-free arm intentionally still pays for complete text inventory/hash
scans and fresh linear search. It does not hide those costs as setup. R0.3 removes
read reconstruction, but graph-enabled retrieval still loads/validates/packs its
stored graph and proof; the observed difference is not merely an enrichment
switch. Candidate indexing records 276 text files and 2,469,239 scanned bytes;
the graph arm records 2,534 symbols, 18,646 calls, 11,215 references, 3,091 type
relations and 4,728 graph edges across these snapshots. Broader candidate text
eligibility explains the different file counts; it is not a matched parser test.

## Recommendation and unresolved questions

My architectural judgment: these results do **not justify eager semantic state
as mandatory infrastructure for ordinary source acquisition**. They demonstrate
valuable semantic evidence and target discovery, but not enough agent benefit to
price that value against the measured costs or establish that eagerness is needed.

Recommend **a separate demand-driven semantic analysis experiment**. This
ablation shows that trustworthy source acquisition can survive without eager
semantic state, with much lower measured resource cost, while precise binding
and some useful target discovery remain losses. A next experiment should test
whether explicit, local semantic questions can recover the demonstrated value
without charging every source request for a repository-wide persistent graph.
Use the alias/reexport/configuration and reverse-caller cases already present,
strict complete proof, acquisition coverage and full costs. That is a
recommendation only; no such implementation or campaign was started.

Keep R0.3 as the graph-enabled experimental reference. Do not integrate this
file-only arm as a replacement on this evidence. It lacks semantic capability,
loses bounded acquisition in two cases and has not established agent outcomes.
Its scanner is bounded to 4,096 text files, 2 MiB per file, 64 MiB per scan and
three results; exclusions and limits are explicit. Nongit directories use root
ignore rules, whereas Git roots use Git's full ignore machinery. Concurrent
writer behavior and larger/cross-platform repositories are unmeasured.

These questions genuinely need agent-level evidence if a later decision depends
on them: whether agents choose better follow-ups and recover the Anvil/Rust
misses; whether pre-resolved bindings reduce wrong conclusions about aliases,
visibility, ambiguous exports and possible configuration; and whether tool-call
savings outweigh prompt and reasoning costs in completed tasks. A model campaign
is not needed to finish this deterministic comparison and was not launched.

## Preservation and reproduction

Both complete paired results passed independent replay: **144 case executions
each, 288 in total**, plus the four-execution smoke. Each full result's exact
466-file manifest was independently recomputed. Commands, external manifest
pins, worker inventories, graph-free module/store checks and retained packet-proof
qualifications are in [replay.json](replay.json). All sixteen full worker suites
completed; all owned runtime directories and execution worktrees were removed.
The implementation worktree and raw evidence remain. Both main working trees
(`/Users/brummerv/loci` and `/Users/brummerv/phluxxed/loci`) and the prior R0.3
worktree retained HEAD, staging, dirty/untracked inventory and file bytes; see
[preservation-after.json](preservation-after.json).

Raw results, exact evaluator sources, manifests, indexes, source envelopes,
resource receipts and the original failed smoke attempt remain preserved. The successful smoke required one harness
import-path fix; no retrieval/scoring policy changed. The directly relevant
candidate and harness checks passed: **23 tests**. All five negative proof-support
checks and byte corruption rejection are included.


Reproduce capability scoring without original execution stores/worktrees:

```sh
PYTHONPATH=src /Users/brummerv/phluxxed/loci/.venv/bin/python -B -m benchmarks.architecture verify --output .scratch/r04-graph-free/results/graph-free-full
PYTHONPATH=src /Users/brummerv/phluxxed/loci/.venv/bin/python -B -m benchmarks.architecture verify --output .scratch/r04-graph-free/results/original-r03-full
python3 .scratch/r04-graph-free/summarize.py
```

Use this worktree/evidence-only descendant so evaluator source hashes match.
For fresh timing measurements use the `run` commands and implementation refs in
the retained `config.json`/`result.json`, a new output directory, `--operation
acquisition`, both enrichment flags `on`, and `--repetitions 2`. Only the file-only
arm sets `--variant-architecture graph-free`. No production branch was modified.
