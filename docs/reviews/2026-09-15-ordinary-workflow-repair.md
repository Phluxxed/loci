# Function-only type paths and short source references

The two selected W1.8.4.4 workflow repairs are implemented and locally verified.
A query containing only `captureCommandResult` now delivers the complete
function-to-options-to-binding proof. Normal retrieval and source paging return
30-character source handles, while Loci retains and validates the full locator.
The current Codex host still runs the old code and requires a restart.

## Deterministic input context

The scheduler gives each selected callable one representative supported input
path before normal family interleaving resumes. It chooses the first authored
input with a supported contract dependency and that input's first authored
dependency; otherwise it prioritizes the first supported direct input. Explicit
selected pairs retain their existing precedence. This uses existing resolved
type edges and complete proof rather than names, prefixes or a new agent mode.

TypeScript input position is checked against the outer parameter field of the
bounded indexed signature using the existing syntax parser, once per callable.
Generic constraints and body annotations cannot masquerade as the parameter
list. Signatures that cannot establish this position, including unsupported
multiline forms, remain ordinary edges. Ambiguous nested `type_argument` roles
receive no inferred input priority. Other supported language roles use their
extractors' controlled parameter observations.

The early path and later ordinary traversal share one admitted neighborhood per
node, so priority does not create a second neighbor allowance. A path advances
only after proof and packing succeed. The two-hop, node, neighbor, source and
complete-output budgets remain unchanged.

An initial implementation prioritized every contract branch. It recovered the
binding proof but crowded out both retained browser call controls. The final
single-path priority preserves those controls and returns remaining branches to
the normal scheduler. A text-based parameter check also misclassified a generic
constraint; structural syntax evidence replaced it before acceptance.

## Exact reads with short handles

The normal tool interface stays `loci_retrieve(repo, query/seed_ids)` and
`loci_read(repo, source_ref)`. Default returned references are deterministic
30-character handles. A per-repository SQLite store in the configured index
namespace retains the canonical repository, path, full content hash and owning
byte extent. The format contains no request timestamp or random identifier.

Packing stages references in memory, then atomically stores only references in
the final successful packet/page. The store keeps at most 8,192 references and
8 MiB of logical locator payload, evicting older entries while retaining the
current response's entries. This bound excludes SQLite bookkeeping overhead.
Persisted handles survive process restart; unknown or evicted handles require
fresh retrieval. They are locators, not authorization credentials.

Reads retain current-index and live-file hash checks, source/control eligibility,
repository isolation, contained paths, ordered offsets and UTF-8 boundaries.
Legacy encoded locators remain readable. Corrupt or colliding references fail
closed; storage failures are explicit. Exact pages remain limited to 8,192 source
bytes and 16,384 complete MCP-envelope bytes. The normal skill and tool contracts
describe short-reference continuation and recovery.

## Validation

The 66 distinct directly relevant tests passed across the storage, normal-source,
signature scheduler, existing retrieval/read, normal acceptance and MCP suites.
Coverage includes atomic concurrent persistence, collision/corruption/eviction,
exact paging, staleness before/after refresh, repository and symlink containment,
neighbor caps across stages, failed proof transitions, generic constraints and a
fresh stdio process resolving an existing handle. Overlapping suite runs are not
counted as extra tests.

The retained-source local check used an isolated store and verified all 638
original file hashes with no extras or symlinks before and after:

| Request | Required evidence | Complete output bytes |
| --- | --- | ---: |
| `captureCommandResult` | Function → Options → Binding | 16,268 |
| Original richer question | Both type edges | 14,846 |
| Explicit Options/Binding pair | Imported binding proof | 16,161 |
| Binding file | Exact source and linked proof | 16,162 |
| `runBrowserCli` | Forward body call and reverse caller, with import/barrel proof | 16,245 |
| `renderActiveTask` | Forward body call and reverse caller | 15,523 |

Every returned source hash/span and linked relationship proof validates. The
function's full 4,468-byte extent reconstructs in one page; the binding file's
14,082 bytes reconstruct in two pages through short handles. The ordering repair
was also demonstrated with legacy long references before integration, so its
effect is not attributed solely to representation savings.

All 45/28/46 artifact inputs from the earlier normal, repaired-v1 and repaired-v2
freezes remain unchanged. The newly selected product and installed instruction
changes are intentional and separate from those historical artifacts.

## Actual host and next step

One actual-host `loci_retrieve` with the same function-only question returned the
exact full native result retained in v2's first attempt: 15,932 bytes, four long
item references of 284/280/291/280 characters, and the old three relationships.
It did not deliver the new input-options path. This establishes the loaded-code
restart requirement, not activation of the repaired implementation. The retained
host receipt makes no completed-provider-interval or full outer-delivery claim.

**Next: restart Codex, then continue W1.8.4.4 with actual-host verification of the
same function-only request and short-reference reads.** Local and stdio tests do
not substitute for that check. No new agent comparison ran here: the measured
1.9216-times baseline input result, strict-answer qualifications and broader
ordinary-value gate remain open. Shorter handles and improved local context do
not themselves prove token savings. Any new provider comparison requires its own
selection and pre-outcome freeze.

Evidence: [repair contract](../../.scratch/deterministic-graph-retrieval/ordinary-workflow-repair.md),
[local results](../../.scratch/deterministic-graph-retrieval/diagnosis/ordinary-workflow/local-results.json),
[host check](../../.scratch/deterministic-graph-retrieval/diagnosis/ordinary-workflow/host-check.json),
[signature replay](../../.scratch/deterministic-graph-retrieval/diagnosis/signature-path-replay.json),
[frozen artifacts](../../.scratch/deterministic-graph-retrieval/diagnosis/ordinary-workflow/frozen-artifact-check.json).
