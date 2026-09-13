# W4.7 frozen evaluator defects

W4.7 (`task_ecbfc0ce724b713f2599830d21438a46`) exposed two evaluator boundary
defects first in `python_alias_annotation-r1-A`, with an additional seed-count
contract mismatch found in the completed Python/JavaScript slice. Preparation source is
`c910c5ac252a7c982f784d87d61bc4c50fc0c0ec`; the separate freeze is
`14cdf4c3061a74060e51cd7c682b56a40b9f1f9e`. The frozen code, schedule and result
remain unchanged. This diagnosis does not calculate replacement metrics or
authorize a corrected provider batch.

## Graph delivery reconciliation

The adapter records a graph call's public name in its delivery ledger, such as
`graph_imports`, and the internal name `graph` in its source trace. The frozen
[multilingual reconciler](../../benchmarks/multilingual_context_observed.py)
uses `graph` for both comparisons. Every delivered `graph_*` call therefore
fails the ledger operation-name check, even when all other fields agree.

The [first result](../../benchmarks/results/multilingual-context-workflow-v1/python_alias_annotation-r1-A/result.json),
[raw host events](../../benchmarks/results/multilingual-context-workflow-v1/python_alias_annotation-r1-A/events.json)
and [adapter trace](../../benchmarks/results/multilingual-context-workflow-v1/python_alias_annotation-r1-A/adapter-trace.json)
establish the mismatch:

| Host item | Ledger name | Source-trace name | Other compared fields |
| --- | --- | --- | --- |
| `item_8` | `graph_imports` | `graph` | Normalized arguments, compact response JSON, serialized bytes and spans agree |
| `item_9` | `graph_imports` | `graph` | All agree |
| `item_12` | `graph_references` | `graph` | All agree, including the pagination-error response |

`unmatched_recorded_delivery` follows from rejecting those rows before marking
their trace IDs as matched. The defect affects graph anchors, neighbors,
traversal, paths, retrieval, imports, references and calls in **either arm**.
Search, get, file, grep, outline and `loci_explore` do not have this particular
name mismatch.

The older corrected
[TypeScript reconciler](../../benchmarks/typescript_context_explore_v2_observed.py)
already separates `_ledger_operation` and `_trace_operation`. The multilingual
implementation did not preserve that separation. This is an evaluator defect;
the inspected payloads do not demonstrate a false Loci source or relationship.

## Pagination contract

The published graph-record schema permits an integer `limit`, and the shared
[normalizer](../../benchmarks/typescript_context_tools_v3.py) accepts `50`.
The [adapter](../../benchmarks/typescript_context_adapter.py) then applies an
undisclosed maximum of 32. The first attempt's `graph_references` call with
`limit: 50` consequently returns `invalid record pagination`. The request never
reaches a Loci graph-record service response.

This schema/adapter disagreement is independent of the ledger-name defect.
Its structured error, read and cost remain in the frozen result. It does not
establish an engine resolution or provenance defect.

## Explicit seed-count contract

Three calls in the first 48 results hit another hidden adapter bound:
`python_unproven_contracts-r1-B` uses six `graph_neighbors` seeds;
`javascript_unproven_dependencies-r1-A` uses seven `graph_retrieve` seeds; and
`javascript_unproven_dependencies-r3-A` uses seven `graph_neighbors` seeds.
Their published array schemas have no `maxItems`, and normalization accepts
the requests. Dispatch applies the frozen five-anchor maximum and returns
`explicit IDs exceed the frozen node/anchor limit` before service delivery.
The effective schema should expose that bound. These retained errors establish
a contract mismatch, not incorrect engine resolution.

## Required Go and Rust control-file access

Eight exact `file("go.mod")` requests in the Go results return
`File not found in cache`, despite the path passing the adapter's frozen
snapshot-file check. The shared adapter calls `service.get_cached_file`, which
requires a mirrored indexed source file. `.mod` is outside the indexable source
extensions. Explore separately recognizes Go controls and can include their
full source as proof.

For example,
[`go_alias_generic_contract-r2-B`](../../benchmarks/results/multilingual-context-workflow-v1/go_alias_generic_contract-r2-B/adapter-trace.json)
retains the failed exact request alongside successfully delivered explore
evidence. All six `go_unproven_package_uses` attempts also retain this exact
failure. Every Go case requires the module-control interval; all twelve A rows
miss it, while ten B rows deliver it. Some omissions occur without an exact
file request, so the eight observed failures do not explain every individual
omission. They establish an access asymmetry in the comparison's exposed tool
surface, not a false Go resolver origin or proof.

This limitation also exists on the normal MCP exact-retrieval surface:
`loci_file` delegates to the same cache-only service, and normal/frozen grep
search the same mirrored source store. Search, outline and get likewise use
indexed source. Graph metadata can name `go.mod` but does not supply its complete
control-source interval. Source inspection therefore establishes no published
Arm A route to satisfy this required interval; only B's special explore control
hydration can do so. This is a product exact-retrieval limitation compounded by
an asymmetric benchmark requirement. It prevents interpreting Go coverage or
call differences as a fair comparison of equally available required source.

Rust demonstrates the same restriction: ten exact `Cargo.toml` reads return
cache misses (eight A, two B), while exploration reads and hash-verifies the
contained manifest source separately. `.toml` is not an indexed source extension.
Every Rust A attempt misses required manifest source; eleven B attempts deliver
all required control source. The normal MCP file/grep paths have the same
restriction. Required Cargo source therefore also lacks an Arm A retrieval
route, precluding an equal-access Rust comparison. See
[`rust_contained_optional_reexport-r1-A`](../../benchmarks/results/multilingual-context-workflow-v1/rust_contained_optional_reexport-r1-A/adapter-trace.json)
and the [successful B packet](../../benchmarks/results/multilingual-context-workflow-v1/rust_contained_optional_reexport-r1-B/events.json).

## Why preparation passed

The [scorer proof](../../benchmarks/comparisons/multilingual-context-workflow-v1/scorer-verification.json)
uses actual explore packets and fresh indexes. The
[transport proof](../../benchmarks/comparisons/multilingual-context-workflow-v1/transport-verification.json)
crosses exact get, explore and an explore schema error. Neither proof crosses
a graph call through the multilingual reconciler. The new observed-delivery
tests likewise exercise explore; the older graph-name regression exercises the
older corrected reconciler. Shared-schema equality tests do not establish
schema/dispatch pagination or explicit-seed agreement. Those passing checks retain their actual
scope and do not validate these missed boundaries.

## What the frozen result can support

The first result directly retains 12 terminal tool calls, the final answer,
provider usage, timing, exact host payloads, ledger rows, source spans and
failure records. Its frozen source-trace recall is 6/6. It correctly remains
`measurement_complete: false`, `tool_delivery_verified: false` and
`full_pass: false` because complete observed accounting was not certified.

The null complete output bytes, aggregate source bytes and source-token estimate
stay null. The retained `recorded_payload_bytes: 10095` subtotal cannot replace
complete accounting. Graph responses rejected at this boundary cannot earn
replacement relationship credit. The report's accounting/trust withhold must
be explained as a measurement limitation, without relabeling it as invented
source or certainty. Direct call, usage and timing observations may be listed;
they cannot establish an efficiency recommendation whose other gates are missing.

There is also an independent answer failure: gold requires
`"payload_origin": "schema.py"`, while the model returned
`"payload_origin": ["schema.py", "Payload"]`. The file origin is correct but
the JSON shape is wrong. Correct source delivery does not make that answer a
pass, and this observation does not authorize a reliability study.

The ordinary prompt names `payload_origin` without prescribing its exact value
shape or endpoint notation. This frozen exact-answer failure is consequently
not, by itself, a demonstrated misunderstanding of the source. Apply the same
distinction to other encoding/structure mismatches; separately retain actual
wrong expressions or claims that ambiguous targets are exact. No score changes
follow from this interpretation limit.

## Deferred remediation

A future, separately authorized harness change should separate ledger and trace
names; exercise every graph operation's exact arguments, bytes, spans and trace
IDs; align pagination constraints across public schema, normalization and
dispatch, including explicit seed counts; provide a truthful exact-read route
for required control files; and add actual graph and control-file transport to
the preflight. Deterministic
remediation can be evaluated without a provider batch. Any later comparison
requires its own authorization, version and pre-outcome freeze. Preserve this
batch, failed gates, original corpus and historical results in all cases.
