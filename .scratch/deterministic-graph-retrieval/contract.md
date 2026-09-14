# Normal retrieval contract — W1.7.2.1

Status: frozen for implementation, 14 September 2026

This contract implements Vik's selected direction in spec.md. It owns the
normal request and deterministic policy; Manifest remains task authority.
Policy version: `normal-graph-v1`. Schema version: 1 for the new operations.
Exact request/response shapes are frozen in `contract.schema.json` beside this
document. Its definitions and the semantic/linking rules below are both
normative. The standard structured error shape remains `{error:{code,message,
details}}`, including for read validation and source-free budget failures.
String byte limits require runtime UTF-8 validation; JSON Schema character
length is not a substitute. The schema uses `x-maxUtf8Bytes` for this rule.

## Public operations and migration

The default `loci-mcp` surface exposes `loci_retrieve(repo, query="",
seed_ids=None)` and `loci_read(repo, source_ref)`. No other retrieval tool is
registered in the default surface. Repository refresh is automatic. Maintenance
and the existing 21 operations remain available only in an operator-selected
`LOCI_MCP_SURFACE=diagnostic` process. An unset value means `normal`; invalid
values fail startup. There is no tool to change the surface. Existing Python
and CLI diagnostic contracts remain compatible. The maintained installers and
guidance must use the normal surface; old catalog clients need a restart.

`loci_retrieve` accepts an existing local repository, a string of at most 4096
UTF-8 bytes and zero to five unique exact indexed node IDs. At least a nonblank
query or one ID is required. Explicit IDs select anchors; a simultaneous query
ranks their context. Invalid IDs fail together with the missing IDs reported.
No regex, intent, direction, family, resolution, hop or budget argument exists.
Unknown arguments fail validation rather than being silently ignored.

`loci_read` expands one exact, hash-bound source extent. Retrieval results issue
the locators used in the ordinary workflow; issuance is not an authentication
or provenance claim and the server does not maintain a receipt registry.
It accepts no query, path, symbol name, line range or traversal controls. A
source reference is versioned URL-safe base64 of canonical JSON containing the
canonical repository identity, relative file, indexed file hash, owning extent
start/end bytes and next byte offset. It is an exact locator, not an access
credential. Validate every field, repository containment, indexed eligibility,
UTF-8 boundaries, extent and current hash before reading. A changed snapshot
returns `SOURCE_STALE`; it never reinterprets old offsets in new source. A page
returns up to 8192 source bytes within a 16384-byte complete MCP result and an
opaque next reference when necessary. It cannot discover another identity.
References are stable across process restart for unchanged source.
The payload uses exactly `{v:1,repo,file,hash,start,end,offset}`. Hash is SHA-256;
byte offsets are nonnegative integers with `start <= offset <= end` and the
owning extent contained in the indexed file. Each returned source has a locator
for its exact span; each item additionally has a locator for its full owning
extent, so a preview can be expanded. These are locators for exact source,
including proof/control source, rather than an assertion of prior server
issuance. No graph policy can be selected through this operation.

## Anchor selection and coverage

Reuse `graph/anchors.py::select_graph_anchors` for symbol/name/signature/path
matching, term normalization, corpus weighting and stable score/file/ID ties.
Explicit seeds retain caller order. Query selection retains up to three
candidates, using the existing corpus cap. Each candidate retains its ID,
matched terms, match scope and score. Several matches are alternatives, not
a proved identity; report their count and omitted candidates. A single retained
candidate is not a uniqueness claim when other candidates were omitted.

Known file IDs and an exact indexed relative file path are valid anchors. Before
symbol matching, trim query whitespace and one leading `./`; when the entire
remaining query equals one indexed POSIX relative file path, select that unique
file. Matching is case-sensitive; do not resolve `..`, absolute paths or outside
links as file queries. Otherwise the unchanged query follows normal matching.
This is source identity recognition, not intent classification. File
anchors expose bounded source and the same traversal policy. For literal text
that has no symbol metadata match, search the exact query as a literal in
hash-verified indexed source, in relative-path/byte-offset order. Select the
smallest containing indexed symbol, otherwise the containing file. No regex
or model classification is used. Stop after 32 MiB scanned bytes, 4096 files or
256 matching locations and report unscanned work. Literal matching is a fallback
for anchor discovery only; it never changes graph eligibility or traversal.
Unsupported files remain outside indexed-source coverage, as today.

Report source coverage from the index and the actual matching scope. Empty or
bounded matching never claims repository-wide absence. Refresh failure returns
the existing structured error and no alleged fresh evidence.

## Structural traversal

Use existing resolved records in the built-in `loci` namespace. Include exact,
declared and import-resolved relationships; exclude heuristic relations.
Preserve `declared_possible` Rust configuration as possible, never unconditional.
Unresolved, ambiguous, external, unsupported and inaccessible records contribute
omissions, not invented edges. Profile/contribution graph diagnostics remain
available separately; this policy does not reinterpret extension edges without
the required source-proof records.

For every anchor, inspect both directions of these four families:

1. Calls: `calls`.
2. Types: `uses_type`, `extends`, `implements`, `embeds`, `supertrait`,
   `impl_trait`, `impl_self_type`, `references_type`.
3. Values: `references`.
4. Imports: `imports`, `imports_type`, with their native resolved endpoints.

Incoming edges keep their stored direction and say `traversed=reverse`.
Direction is not inferred from question wording. The same eligible families
apply at every depth and in every supported language; only existing resolver
evidence governs whether a relationship exists. In particular TypeScript,
Python, Go and Rust calls/values are not suppressed by the old JavaScript-only
dependency filter. No runtime dispatch or callback-flow reconstruction is added.

Traversal is breadth first, at most two semantic edges from each anchor.
Within each depth, interleave anchors in their selected order and then the
nonempty `(family,direction)` queues in family order above, forward before
reverse. Take one candidate per queue per round, repeating until exhausted or
the work limit is reached. Before interleaving, rank each queue by descending
query-term overlap with target name/path/signature, then ascending eligible
target degree, then target ID, edge type, from/to ID, evidence file/line/hash,
and traversal direction. Eligible target degree is the number of distinct
eligible native edge identities incident to that node over both directions,
before query/anchor/neighbor filtering; count a self-edge once. The universe is
exactly the four built-in families and allowed resolutions above. Query terms
change ordering only; zero-overlap
relationships remain eligible. No floating-point score or time cutoff controls
the traversal order.

Count unique examined node identities, not queue entries. Expand each identity
once at its earliest shortest path; retain the first stable proof path. Report
alternative paths and cycles. Deduplicate identical edges using the complete
edge identity including evidence hash and resolution. Do not merge several
records by line alone when that could combine different source proof.

Limits are maintained policy constants: three inferred/five explicit anchors,
two semantic hops, 64 examined nodes, 32 selected neighbors per expanded node,
12 delivered source items, 8192 unique source bytes and 16384 bytes for the
complete successful MCP result. Neighbor selection uses the same family rounds
before clipping; count all excluded eligible neighbors. Limits and policy ID
are returned, and changing them requires a new policy version. There is no
per-request override. This fixed version is sufficient host configuration;
configurable alternative profiles are not part of this change.

## File and package context

A symbol's containing file is an exact source-ownership association, not a
semantic dependency. Lift to that file to inspect imports. Preserve the
`file -> file/package/module/crate` stored import endpoint; never rewrite it
as `symbol -> symbol`. Display ownership associations separately from
`relationships` so accounting cannot count them as semantic graph edges.

For a selected file/module/package/crate, choose at most three source-backed
declarations through validated ownership metadata: exact `file_path` for a
file, indexed Go files in the Go package's exact `directory`, the Rust crate's
exact `crate_root`, and indexed Swift files under its declared module directory.
Rank by descending query-term overlap with name/path/signature and then
file/start-byte/ID; retain zero-overlap candidates only when no candidate
matches. Ownership selection consumes the same global node/item budgets but
no semantic hop. Visit each owner/member association once; preserve first-path
selection and do not recursively bounce between a file and its declarations.
Process this finite ownership selection before advancing to the next semantic
depth. Source-backed member items remain distinct from native endpoints.

There are no stored non-Markdown containment edges to claim here. The symbol's
same-file owner, package directory, crate root and module directory are indexed
ownership facts. No filename guess substitutes for validated resolver metadata.
File endpoints use their indexed identity and current file hash, with no
synthetic definition snippet. Go packages require package-clause source and
current Go controls. Rust crates require crate-root identity, named Cargo
controls and relevant module/configuration source; keep declared possibility.
Swift module proof requires its Package.swift target source; when a complete
unique target declaration cannot be hydrated, report `proof_unavailable`.

Import records retain a source hash and physical line, not trustworthy byte
extents for every language. Recover a complete unique enclosing declaration by
parsing the hash-verified cached source, checking recorded line and authored
import identity. Reuse the existing Go/Rust declaration readers and add the
corresponding Python/JavaScript/TypeScript/Swift statement readers. A parse
failure or several matching statements is `proof_unavailable`; never degrade a
complete-statement promise to an opening line. The resolver itself is unchanged.
JS/TS package/tsconfig/workspace controls named by resolution must also be
hydrated from tracked, contained, hash-equal control files; unsupported controls
cause proof omission, not an unqualified relationship.

## Source packing and repeatability

Assemble proof and selected source before claiming delivery. A normal item
contains its exact identity, kind/file, anchor/related role, traversal depth,
selection explanation, source IDs, full owning source extent and source_ref.
`complete` means the full owning source extent was delivered. Preview at most
1024 UTF-8 bytes of each anchor and 768 bytes of each related declaration,
preferring complete lines and never splitting a UTF-8 code point. Mark previews
incomplete. Exact proof spans are additional and cannot be clipped into a claim
of complete proof. Known control and import/export declarations must be whole.

The result contains `schema_version`, `policy`, `snapshot`, `status`, `selection`, `scope`,
`anchors`, `nodes`, `items`, `ownership`, `relationships`, `sources`, `omissions`,
`limits`, and `usage`. `snapshot` is a SHA-256 over canonical sorted indexed
source/control hashes and graph schema identity, excluding cache paths and
timestamps. Source records use the existing exact byte/line/file/hash
shape. Relationship records retain edge, traversal direction, configuration
qualification and all supporting source IDs. Each delivered relationship must
have both endpoint identities in `nodes` and a complete source-proof chain in
the same result. `nodes` contains identity/name/kind/file metadata for delivered
items, native relationship endpoints and their required ownership links; it
does not invent source for package identities. Ownership may connect a symbol
to a native file endpoint but cannot
stand in for a missing semantic edge. One native relation is counted once even
when it supports multiple selected items.

Packing follows deterministic traversal order, skipping a bundle that cannot
fit, and may still accept a later smaller bundle. Budgets include the entire
MCP envelope and all policy/omission/reference fields. Deduplicate overlapping
source byte extents for evidence accounting. Never leave orphan proof/source
references when omitting a bundle. A large anchor preview cannot consume the
whole source budget before relationship packing. If mandatory framing cannot
fit, return a source-free structured budget error.

`usage` reports unique nodes examined, eligible edges considered, traversed
edges and delivered relationships separately, evidence bytes, complete result
bytes and byte-based token estimate. These are observed execution counts;
the operation name alone does not prove traversal. Successful zero-edge calls
still execute policy selection. `status` is `ok`, `partial` or `empty`.
Omissions distinguish no anchor, candidate/work/item/hop limits, cycle,
alternative path, unsupported semantics, unresolved/ambiguous/external records,
source unavailable/stale, source preview, proof unavailable and byte budgets.
All absence claims remain non-exhaustive.

No hidden mutable cursor exists. Repeat the same snapshot/request/policy and
receive the same semantic selection/order. Follow a returned exact identity
through `loci_retrieve` to re-anchor under the same policy, or use `loci_read`
to expand its exact source. Re-anchoring is a new bounded request and does not
guarantee enumerating every omitted neighbor. A repeated identical request is
not advertised as progress. Transport request IDs and timing are excluded from
repeatability; policy/source identities and omissions are included.

## Implementation ownership

Add a normal retrieval module behind `service.retrieve` and `service.read`.
Reuse anchor selection, validated graph state, cached-source verification,
declaration/control proof readers, graph records and source span primitives.
The legacy intent-specific selector remains diagnostic. Extract shared helpers
only where both selectors actually need them; avoid a generic policy framework.
Normal packing may have its own envelope because the existing packer assumes
intent, one definition source and symbol-only ancestors. Keep common exact
span validation and byte accounting shared where contracts are identical.

`mcp_server.py` owns default versus diagnostic registration and strict normal
arguments; `mcp_output_models.py` owns published output schemas. Installers,
launchers and canonical skill changes are W1.7.1/W1.7.3. The concurrent catalog
and multiline TypeScript export-proof corrections remain W1.7.4/W1.7.5.
No benchmark case names, answer spans or task IDs enter product code.

## Required independent fixtures

Exercise normal service and actual MCP calls with generated/renamed source:

- A function with a local callee, imported value/type, and caller; the packet
  contains both directions with exact proof and no intent argument.
- A same-name type behind a multiline barrel beside a different view type;
  preserve identity, full export statement and generic-shadow rejection.
- An import-only file and a Go package/Rust module target: preserve native
  endpoints and source/control proof; ownership is not a semantic edge.
- Same-name candidates in different files, an unrelated decoy, and a literal
  present only inside a body; retain ambiguity and bounded discovery scope.
- Cycles, repeated paths, broad families and a high-degree node; deterministic
  family allocation, cycle handling and budgets survive insertion-order and
  filesystem enumeration changes.
- A large anchor with a short meaningful relationship; preview plus proof
  fits, hydration expands exactly, and source changes refuse old references.
- No eligible relationships, unsupported language, unresolved/dynamic calls,
  stale proof and insufficient budgets: honest outcomes without forged edges.
- Default catalog contains only normal operations; diagnostic compatibility is
  explicitly configured; unknown mode/control fields are rejected.

Tests assert observable packets and safety limits, not copied internal ranking
implementation. Frozen task gold remains evaluation-only.

### Concrete independent packet examples

Use a small TypeScript fixture with `schema.ts` defining `WireEnvelope` and
the distinct `WireEnvelopeView`; `public.ts` re-exports both in one multiline
statement. `assemble.ts` imports `WireEnvelope`, defines `encodeEnvelope`,
and defines `assembleEnvelope(value: WireEnvelope)` calling `encodeEnvelope`.
`entry.ts` imports and calls `assembleEnvelope`. Keep each definition below
512 bytes and the complete combined source below 4096 bytes.

For `loci_retrieve(repo=fixture, query="assembleEnvelope")`, expected packet
facts (IDs use the actual parser output rather than guessed IDs) are:

| Delivered fact | Stored direction | Traversal | Required source |
| --- | --- | --- | --- |
| `assembleEnvelope` is the best matching anchor | none | none | exact definition |
| `assembleEnvelope` calls `encodeEnvelope` | assemble → encode | forward | exact call and callee definition |
| entry caller calls `assembleEnvelope` | entry caller → assemble | reverse | call, import and target definition |
| parameter uses `WireEnvelope` | assemble → WireEnvelope | forward | type site, import, complete multiline export, definition |
| `assemble.ts` imports `public.ts` | file → file | forward | whole import statement and resolved target identity |

`WireEnvelopeView` is never substituted for `WireEnvelope`. The owning-file
association is not counted as a fifth semantic relationship. All source IDs
resolve; spans equal cached source bytes at the returned hashes; no intent or
edge flag appears in the request. Rename every declaration and file, update
the query, and the corresponding structural packet still passes.

For a no-edge Markdown declaration selected by exact ID, expect an anchor
source item, executed policy accounting, zero semantic relationships,
non-exhaustive scope and supported zero/unsupported explanation. For a large
function in the same graph fixture, expect `complete=false`, a bounded exact
prefix and an exact source reference; reading all pages reconstructs its
indexed extent byte for byte. Editing the file between retrieval and reading
must return `SOURCE_STALE` with no source.

## Ordinary value acceptance

Preserve all original 14 outcomes, eight fresh reserved ordinary rows and two
separate known-answer primary checks. No extra trials, reminders or replacement
runs are selected. Freeze product, catalog, installed guidance, observer adapter
and these gates before run 15. Baseline rows are never rescored.

1. All 8/8 ordinary rows retain the fixed source/prompt/rubric, required capture
   and requested model/effort, within the existing five-minute execution cap.
   Preserve the 60-operation/400000-visible-byte accounting flags as reported
   flags, not hidden answer-scoring failures. All 8/8 answers
   satisfy every frozen required fact with no materially unsupported claim.
2. At least 4/8 ordinary rows deliver a source-backed semantic relationship
   through normal retrieval with a retained `full_exact` model-visible output
   reference, including at least 3/4 binding/browser rows and
   at least one of each of those cases. At least 2/8 final answers have a
   reviewer-validated relationship-support annotation tied to successful normal
   context with complete proof and `full_exact` model-visible delivery. This is
   an outcome gate for context delivery, not a quota
   imposed on agents. Exact-source answers remain correct, including renderer
   tasks where graph context can legitimately add nothing.
3. Both primary checks use the loaded normal operation and return the expected
   relationship with complete proof in a retained actual-host `full_exact`
   model-output reference and verified proof IDs. They remain known-answer functional
   checks outside the ordinary denominator and cost comparisons.
4. For each case's two ordinary post rows, median visible bytes, provider input
   tokens and elapsed time must each be no more than 1.25 times the matching
   original ordinary pair's median. Compare unrounded values from retained
   results. Include failures in accounting; missing capture cannot pass. This
   allowance is the predeclared maximum cost tradeoff for fully correct answers
   and relevant graph delivery. It is not an efficiency claim. Publish individual
   values, ranges, call counts and all provider usage alongside medians.

Only describe the result as more efficient when each comparable case's medians
are at or below baseline for all three cost measures and at least one is lower.
Passing the 25% allowance supports bounded cost increase only. More graph calls
alone cannot pass any value claim. Report failures or an inconclusive result
without replacement trials or weakening thresholds. The sample cannot prove
population adoption, internal model reliance, statistical significance or
causal benefit from graph use.

Use a versioned adapter around the existing observer. Recognize normal
retrieval/source reads, retain semantic edge counts, and separately validate
that relationship source IDs resolve and contain matching evidence file/hash/
line. Malformed proof is unknown/invalid, never silently zero. Count ownership
separately. Reuse model-visible delivery correlation and existing answer-support
annotations. Preserve baseline helpers and outcomes; no new telemetry store or
review platform is needed.
