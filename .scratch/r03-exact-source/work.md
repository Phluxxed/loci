# R0.3 exact-source ablation

Terminal outcome: determine whether exact reads can avoid typed full semantic reconstruction with source-access guarantees preserved; fixed paired direct/continuation and negative fixtures, maintained Anvil source, total cost accounting and independent replay. No integration or agent campaign. Base 4cadfe1a233b9ec34b8ef25244d163d64297a8f4.

Assignments before launch:
- read_harness: owns benchmarks/architecture.py, benchmarks/architecture_reads.py and matching harness tests/fixture inputs. Add minimal direct-read mode using existing orchestration/isolation/manifests/replay, independent equivalence+errors. gpt-6-sol/high/fork none.
- source_boundary: bounded decision consultation, read-only src/loci read/freshness/eligibility design, recommend minimal safe separation and challenge assumptions. gpt-6-astra/high/fork none.
- primary: owns candidate src/loci changes, focused guarantee tests, material decisions, experiment execution and synthesis.

source_boundary recommendation: adopted. Use a generation-bound source-access
projection constructed only after existing write-time semantic validation. Bind
both actual index bytes and canonical projection payload by SHA-256. Missing,
corrupt or mismatched projection falls back to existing full graph behavior.
Preserve the complete repository/module/coverage/active-path freshness and writer
lock/recheck; never reduce freshness to the requested file. Locator validation,
live source hashing, containment and UTF-8 pager remain shared. This adds a small
persisted derived artifact, not a graph-free engine; every read still hashes the
full index bytes, and refresh/indexing still compile and validate the graph.

Additional bounded test assignment: source_guarantees, gpt-6-sol/high/fork none,
owns tests/test_source_access.py only. Required gap: directly prove validated
source reads avoid reconstruction, and corruption/fallback/freshness safeguards
are preserved. Acceptance is focused tests plus existing exact-read suite; no
production/global changes or worker-spawned delegation.

Candidate initial checks: 26 existing read/normal-acceptance tests passed, then
106 storage/source-ref/read checks passed. A broader service/retrieval run had
165 passes and two graph-health dictionary expectation failures. Both identical
nodes fail at unchanged control 4cadfe1, so they are pre-existing and not repaired.
An initial command named tests/test_index_store.py incorrectly; the actual suite
is tests/storage/test_index_store.py and was included in the 106 passing checks.

source_boundary reuse: actual candidate implementation now exists; bounded
read-only check requested for the material evidence gap between proposed trust
boundary and implemented generation/fallback/freshness paths. Same Astra/high
worker and retained source context fit this scope. No optimization or extra
architectural scope authorized.

Critical negative finding and correction: source_guarantees demonstrated that a
self-checksummed sidecar could add an unindexed file while retaining genuine
index_sha256. The candidate was corrected before measurement: the canonical
source payload digest is now a final field of validated index.json, and loading
checks that exact footer from the same bytes streamed into the index SHA. Missing
or altered anchors fall back. Graph schema and outer version compatibility also
fall back. Astra's first implementation pass missed the defect; its disposition
is superseded by the executed regression and corrected anchored construction.
The trust root remains the validated local index, not arbitrary sidecar contents.

Validation correction: initial plain-venv pytest commands could import the main
editable package. They are not candidate acceptance evidence. All final candidate
checks use PYTHONPATH=src. The final focused/broad relevant command produced
296 passed and 2 deselected in 9.64 s; deselections are the two independently
verified pre-existing graph-health expectation failures. Source_guarantees owns
16 passing focused tests, including sidecar forgery, missing/changed root footer,
version gate, refresh lock, containment and paging. Go control has a live focused
fixture; timed small corpus will separately cover Cargo and JavaScript controls.
No Swift-specific direct-read fixture has been claimed.

source_boundary final recommendation: adopted with demonstrated-defect correction.
Source payload -> payload digest -> root index footer -> full index-byte digest ->
sidecar avoids circular hashing. No added key/database. Exact-source separation
still hashes all index bytes and refreshes/compiles full semantics when necessary.

read_harness result: adopted after primary inspection. Direct mode extends the
existing runner with an explicit mechanism, fresh reader process, frozen exact
page/error observer, small deterministic suite and paired replay. Concrete gaps
found during inspection (post-read fixture verification, replay inventories and
paired equivalence, required UTF-8 negative inventory) were corrected before
measurement. Final focused exact-source harness suite: 3 passed in 20.19 s.
Primary also ran existing harness/corpus and source projection checks with
PYTHONPATH=src: 26 passed in 26.96 s. Observer and candidate have independent
revision identities. The prospective schedule is protocol.md.

Execution completed at observer be96a7f against control 4cadfe1 and candidate
a38e17d. All six paired comparisons passed, including 24 independently scored
request executions and 36 rejection probes. All three retained replays passed.
Deliberate packet corruption, source corruption, continuation truncation and
missing UTF-8 negative controls were rejected. Twelve store identities were
distinct; all owned execution checkouts/runtime directories were removed.
Both main working states match the initial snapshot (only porcelain's terminal
newline required serialization normalization). No source files were restored
or cleaned in either main repository.

Anvil mean first/repeat/continuation: 3525/3506/3552 ms control versus
126/105/124 ms candidate; reader peak 426.8 versus 55.8 MB. Full indexing
remains about 5 s / 500 MB. Candidate still hashes the full index and retains
graph work during refresh. Recommendation: source decoupling is viable within
demonstrated safeguards; integration is a separate decision. Five semantic
proof discrepancies remain visible and unresolved. RESULTS.md/summary.json and
validation.json contain evidence and limitations. Stop after evidence commit
and explicitly requested branch push; no production integration or campaign.
