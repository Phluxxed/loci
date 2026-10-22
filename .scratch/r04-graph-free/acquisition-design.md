# R0.4 bounded acquisition consultation

Recommendation: retain the original initial-query result, and add one fixed,
source-only followup scheduler shared by every architecture arm. This measures a
particular deterministic acquisition policy. It cannot establish how well a
model would navigate, disambiguate names, interpret uncertainty, or finish a task.

## Frozen acquisition protocol

- Keep the existing frozen entry query from `architecture_cases.requests`.
- Give the scheduler only the initial query, observed packets/source spans, and
  a sorted inventory of relative filenames, sizes and content hashes. Never
  expose gold context spans, required relationships, missing coverage, candidate
  symbols, graph edges, or scorer output. Charge inventory delivery separately.
- Hydrate selected extents in returned order, subject to the shared call/byte
  limits. Continuations are source acquisition and must consume those limits.
- Prefer the first observed file that has not been completely delivered, queried
  by its exact relative path. This exposes imports and nearby declarations around
  narrow symbol extents. Do not query fully covered files again.
- Next prefer paths discovered lexically in delivered text: relative quoted paths
  matched against inventory, then extension-neutral filename stems present as
  whole identifiers. Resolve ambiguity by sorted relative path, retaining all
  alternatives in the queue; this is candidate discovery, never semantic proof.
  A fixed nearest-ancestor manifest lookup may discover `go.mod` and `Cargo.toml`
  from observed source paths, without reading undisclosed source. If implemented,
  its exact manifest list and ordering must be frozen before measurement.
- Finally queue remaining source identifiers in first-observed byte order after
  one fixed keyword/primitive stoplist. Deduplicate queries and file reads.
  Process the queue breadth-first, breaking exact ordering ties lexically.
- Freeze five retrieval calls total, sixteen continuation calls total, 128 KiB
  cumulative delivered source and 256 KiB cumulative response bytes per case.
  These are a bounded exploratory policy, not calibrated optimum budgets.
  If APIs cannot cap the next response, byte limits are admission limits checked
  between calls: retain and charge the full last packet and record overshoot.
  Never truncate a retained packet to manufacture compliance. Call caps are hard.
- Record each query, the source span/path that justified it, each continuation,
  cumulative bytes, outstanding queue, and termination reason. Report initial
  plus final coverage so followup gains and costs remain visible.

The exact lexical implementation is the protocol: freeze its bytes before the
first scored run. No tuning against observed case misses within this comparison.

## Observer adaptation

Keep `architecture_cases._validated_spans`, `_covered`, source union/repetition
accounting, frozen source identity checks and the existing strict semantic scorer.
Use explicit schema dispatch for the graph-free inventory/packets and reject
unknown schemas or semantic claims from a source-only candidate. An internal
empty-symbol/empty-edge projection can satisfy the existing scorer's input shape
only after validating the real graph-free schema; preserve that real schema in
the artifacts. It must not masquerade as a successful ordinary graph index.

Add source anchor coverage independent of graph IDs. The current
`anchor_selection` checks expected symbol IDs against candidate index IDs
(`architecture_cases.py:239-252`), so it is not a common acquisition outcome.
Leave that graph-specific dimension labeled unavailable for a source-only arm,
or preserve its original value alongside the architecture-neutral span measure.

Source coverage and semantic proof remain separate. Source text containing both
endpoints proves neither an edge nor a correct consumer answer. Empty graph-free
claims give zero positive proof credit; avoiding forbidden claims alone is
vacuous and should be labeled as no semantic claims made. Preserve graph-arm
proof failures explicitly rather than waiving them to produce a valid aggregate.
Raw source-coverage measurements can still be reported with their independent
validation status when a wider graph proof comparison is invalid.

## Evidence and limits

The existing worker performs exactly one query then hydrates every selected item
(`architecture.py:140-164`). The scorer already separates frozen span coverage,
strict relationships, source/repetition bytes, and unobserved task correctness
(`architecture_cases.py:232-293`). This supports a small runner extension rather
than another framework.

Inspected frozen archives: fourteen TypeScript synthetic snapshots contain only
1-4 files and 144-345 bytes each. Most multilingual snapshots contain 1-7 files
and 93-714 bytes. Full fixture coverage therefore often means almost the whole
fixture was delivered. Report unique delivered bytes / total snapshot bytes and
delivered file count / inventory file count, and keep synthetic versus larger
repository-case results visible. The Anvil snapshot has 187 files and 2,442,185
bytes; the Loci Python snapshot is one 17,942-byte file. Those are useful but do
not establish broad real-repository behavior.

Coverage intentionally includes non-symbol import/reexport and package metadata:
`go_alias_generic_contract` requires `go.mod`; the Rust optional reexport case
requires three Cargo manifests; Python impact starts at `target` while its caller
uses `alias`. Identifier-only outbound expansion can miss these for mechanical
reasons. A negative result applies to this frozen acquisition policy, not all
graph-free tools or a capable agent. Conversely high coverage by broad file reads
does not establish disambiguation, forbidden-edge rejection, task success, or
token-efficiency under an agent. No additional agent/model campaign is required
to complete this bounded Level A comparison.
