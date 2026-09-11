# Bounded context from existing type references

W2.2.1 contract, declared before the A/B comparison. The implementation lives
on `feat/evidence-backed-exploration`; the shared Objective remains in the
original Loci checkout. This slice changes retrieval policy and source delivery,
using the existing extractor, resolution records and graph.

## Interface

`loci_get(repo, symbol_ids, context=0, selected_from_search_id=None,
include_type_context=False)` retains its exact response when the flag is false.
When true, it returns the same requested `symbols`, plus `type_context`.
The service composition is `get_symbols_result` with the same arguments and the
existing service-only `ensure_fresh` option. `get_symbols` remains unchanged.
Search, explicit graph retrieval, diagnostics and search-selection lineage
retain their existing meaning. Hydrated dependencies do not inherit selection
lineage from the requested symbols.

There is one opt-in, with fixed conservative limits; no new exploration tool,
query language, configuration file or persistent graph schema is introduced.
An empty or invalid symbol request retains the exact-get error. File, package,
crate, module and Markdown symbols are not type-expansion anchors.

## Selection and proof

1. Retrieve the exact requested source through normal freshness handling.
2. Deduplicate eligible requested IDs and select the first five in lexical ID
   order. Exact root output still preserves caller order and duplicates.
3. Examine validated persisted symbol-reference records in those declarations.
   A record must be resolved, have a type-only binding, and have a matching
   directed `loci/references_type/import-resolved` edge with its original source
   and target IDs. Follow outgoing references only. Target IDs must identify
   real indexed source declarations. Do not infer an edge from matching names,
   ordinary value references, imports alone, unresolved records or file proximity.
4. Ownership uses the record's exact half-open byte interval and source file.
   Its owner is the unique smallest containing real indexed declaration. Ties
   are ambiguous and omitted. A parent does not take references belonging to a
   nested declaration. This is retrieval selection, not a new semantic edge.
5. Keep the original graph edge, including its file-owned source where present.
   Return the selected `owner_id`, target and exact reference byte interval
   separately. Existing edges collapse repeated source/target references: their
   canonical evidence line may belong to an earlier sibling. Select using the
   matching reference record, never that collapsed edge's line alone.
6. Hydrate complete target declarations and authored import/re-export support
   lines from the indexed cache. Every included relationship must have its owner
   and target source available in the response and its support hydrated. Source
   hashes and byte intervals must agree with the cached source. Do not emit a
   relationship if its required evidence cannot be delivered.

The expansion is breadth-first, with at most three dependency hops. Within a
depth, order owners by ID and records by source file, start/end byte and target
ID. Deduplicate definitions by symbol ID, support lines by file and line, and
relationships by owner/target, retaining the first qualifying reference. Already
visited targets are not expanded again; cycles terminate. An already delivered
target may support another relationship without repeating its source.

## Bounds and omissions

The hard limits are five anchors, three hops, 32 visited declaration nodes,
16 outgoing candidates per owner, 16 delivered relationships, 64 source spans,
16,384 delivered source bytes (4,096 estimated tokens) and 32,768 serialized
response bytes. Source/span/response limits include requested source and added
context. Reserve 1,024 serialized bytes for response accounting outside the
service. No item is truncated mid-definition or mid-support line.

Requested exact source has priority and is never truncated by this opt-in. If
the exact response already exceeds a limit, return it with no expansion and an
explicit root-budget omission. The flag therefore bounds additions; it does not
retroactively impose a new size restriction on exact get. Evaluation separately
enforces its existing whole-operation limits on both arms.

Fit a complete definition/relationship/support bundle atomically. If it does
not fit, record the limiting reason and continue to later smaller candidates
within the selection bounds. Do not traverse a target whose source was omitted.
Count and report anchor, ownership, unsupported-target, missing-evidence, node,
neighbor, relationship, hop, source/span and serialized-budget omissions in a
bounded reason-to-count map. Never attach an unbounded list of rejected records.

`type_context` contains `scope`, `status`, `symbols`, `references`, `evidence`,
`limits` and `omissions`. Status is `complete` for an exhausted selected candidate
universe, `partial` when something in that universe was omitted, and `unavailable`
when validated graph state is missing or invalid. A graph failure leaves exact
source available and names the graph error; it does not hide diagnostic failures
on the existing graph tools. No eligible anchor returns a stated omission.

The declared scope is **existing imported type references within uniquely owned
indexed declarations**. An empty result does not prove the declaration has no
type dependencies. Local aliases/types, ordinary-import annotations, explicit
heritage and unsupported syntax remain outside this slice wherever the existing
graph cannot prove them. Nested declaration references are excluded from the
parent's expansion. No repository code or compiler is executed.

## Acceptance and matched comparison

Focused checks cover imported definitions and re-export support, same-file
sibling references sharing a collapsed edge, nested declaration isolation,
generic-shadow and ambiguous-export negatives, deterministic deduplication,
cycles, empty/no-anchor/missing-graph cases, source and output exhaustion,
freshness after a real source edit, and unchanged exact retrieval and lineage.
The host-facing optional field and output schema receive an MCP check.

The evaluator's B arm automatically enables this opt-in on its existing `get`
operation. A uses exact get. Both retain the frozen v3 thirteen typed operations,
resource helpers, common prompt, parameters, source snapshots, gold and budgets.
Thus the model makes the same request; B alone supplies bounded related context.
All extra definitions and support source are included in exact delivery costs.

Freeze the candidate source and new comparison harness before measurement.
Run a fresh 102-attempt matched batch: 17 cases, three repetitions, both arms,
serial A/B, B/A, A/B order. Apply the v3 observed-call, answer, source-recall,
cost and latency gates without changes. Historical A-only results are context,
not the paired comparator. Preserve failures and negative results. Record
whether the policy is kept, adjusted or rejected and identify remaining gaps
from actual stored relations and declaration ownership, without adding new
semantics during the experiment.
