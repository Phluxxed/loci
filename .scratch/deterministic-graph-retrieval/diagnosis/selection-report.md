# W1.8.4.1 selection diagnosis: retained binding proof

## Decision

The missing delivery is a deterministic selection-and-packing failure. The
supported TypeScript relationship is extracted, resolved through the public
barrel, persisted with the correct declaration identities, and fully
hydratable. Normal retrieval attempts that exact edge in all three retained
requests. `RetrievalPacker` rejects the atomic addition because earlier
ownership-driven context and semantic additions have already consumed too much
of the 16,384-byte result envelope.

The bounded repair is to keep a symbol anchor's native file identity and
ownership association, but defer expansion of that owning file and its
unrelated declaration members until direct semantic proof from the selected
anchor(s) has had a chance to pack. For explicit anchors, a relationship whose
two endpoints are both anchors must be considered before unrelated file
members. Exact file anchors must retain their existing member-expansion
behavior. This changes deterministic selection order only; it does not weaken
proof, change extraction/resolution semantics, or raise the public budget.

That repair is sufficient for the `CaptureCommandResultOptions` query and the
explicit pair. It cannot promise that a broad `WorkContextBinding` query will
return this particular consumer: that anchor has 36 eligible direct neighbors,
and the target consumer is ranked 18th (zero-based position 17). A broad
definition query needs bounded representative impact selection; it is not a
request for one known consumer.

## Evidence scope and reproduction

The fixed source is `/tmp/anvil-source-tasks-20260914/t23`, expected Anvil
commit `53bf29e60cece2335aa39fe301935a07e8e8d4e4`. The probe observed all 638
files and built a fresh index in a task-specific temporary store. That store
was removed after the run. Product source, tests, contracts, frozen comparison
artifacts, and the Anvil source were not changed.

The exposed Loci surface contained only `loci_retrieve` and `loci_read`, so the
first pass used normal public retrieval and the second diagnostic pass used
the deterministic local indexing/retrieval APIs against the isolated store.
This is an engineering replay, not a provider or agent trial.

Artifacts:

- [`selection-probe.py`](selection-probe.py) indexes the fixed checkout,
  inspects persisted records, instruments every atomic pack attempt, and runs
  the bounded counterfactuals.
- [`selection-probe-output.json`](selection-probe-output.json) contains the
  complete record/proof provenance, neighbor order, marginal byte accounting,
  and replay summaries.
- Frozen actual-host packets remain unchanged at
  `benchmarks/comparisons/ordinary-adoption-normal-v1/runs/run-23/`.

Reproduction from the repository root:

```sh
probe_store=$(mktemp -d /tmp/selection-loci-store.XXXXXX)
PYTHONDONTWRITEBYTECODE=1 LOCI_BASE_DIR="$probe_store" .venv/bin/python \
  .scratch/deterministic-graph-retrieval/diagnosis/selection-probe.py \
  --repo /tmp/anvil-source-tasks-20260914/t23 \
  --store "$probe_store" \
  --output .scratch/deterministic-graph-retrieval/diagnosis/selection-probe-output.json
rm -rf "$probe_store"
```

The replay passes `coverage="complete"` to the direct API, while the frozen
actual-host packets report `coverage="partial"`; that one-character enum
difference makes each replayed final envelope one byte larger. Topology,
selection, and the target rejection match: 16,374/16,238/16,210 replay bytes
versus 16,373/16,237/16,209 frozen bytes.

## Stored relationship and proof

The isolated index contains exactly one matching projected edge:

```text
src/tool-results/service.ts::CaptureCommandResultOptions#type
  -- uses_type / import-resolved / service.ts:56 -->
src/work-context/binding.ts::WorkContextBinding#type
```

The matching `TypeRelationRecord` is `status=resolved`,
`resolution_basis=reexport_chain`, with the single complete candidate
`src/work-context/binding.ts::WorkContextBinding#type` in the
`src/work-context/index.ts` import surface. Its stored support is:

| Support | Location | Identity |
| --- | --- | --- |
| authored type site | `src/tool-results/service.ts:56` | `CaptureCommandResultOptions` |
| declaration owner | `src/tool-results/service.ts:53` | `CaptureCommandResultOptions` |
| type import | `src/tool-results/service.ts:23` | `src/work-context/index.ts::__file__#file` |
| public type re-export | `src/work-context/index.ts:23-30` | `src/work-context/binding.ts::__file__#file` |
| final definition | `src/work-context/binding.ts:28` | `WorkContextBinding` |
| resolver controls | `package.json`, `tsconfig.json` | exact stored hashes |

`RetrievalSource.proof` returns all eight unique proof spans: the occurrence,
property line, owner declaration line, import declaration, full multiline
re-export, final exported declaration line, and both controls. There is no
`proof_unavailable` event for the target attempt.

This matches the implementation. Imported TypeScript observations cross the
existing export-surface resolver in
[`type_relations.py`](../../../src/loci/graph/type_relations.py#L203), and each
resolved record projects to a `uses_type` edge in the same file at line 336.
Proof assembly verifies the stored record and hydrates its site, support, and
controls in [`_retrieval_source.py`](../../../src/loci/_retrieval_source.py#L106).

## Why each retained request misses

All byte counts below are complete MCP result envelopes, including the
`content`/`structuredContent`/`isError` wrapper. The evidence limit is 8,192
bytes and the output limit is 16,384 bytes.

| Request | Target position and state | Target candidate | Immediate result |
| --- | --- | ---: | --- |
| `CaptureCommandResultOptions` | Target is the anchor's third direct neighbor and fifth semantic attempt after ownership-driven file traversal; state 13,286 B | 19,783 B; evidence 2,894 B | rejected by output budget, 3,399 B over |
| `WorkContextBinding` | 36 direct neighbors; target position 17 and 44th semantic attempt after interleaving ownership visits; state 16,171 B | 19,662 B; evidence 2,685 B | rejected by output budget, 3,278 B over |
| explicit pair + `binding contract` | Query overlap ranks target first and it is the first semantic attempt, but ten context additions precede it; state 13,753 B | 18,292 B; evidence 2,524 B | rejected by output budget, 1,908 B over |

The relevant code first packs `_ownership_lifts`, adds successful lifts back to
the same-depth layer, and only afterward builds the semantic scheduler in
[`retrieval.py`](../../../src/loci/retrieval.py#L138). File endpoints then
select up to three declaration members in
[`_retrieval_source.py`](../../../src/loci/_retrieval_source.py#L146). The
packer applies each source/item/ownership/relationship bundle atomically and
rejects an oversized candidate in
[`_retrieval_output.py`](../../../src/loci/_retrieval_output.py#L120).

For the explicit pair, the two anchors themselves occupy 5,062 B. Before any
semantic edge, the owning files select these six unrelated or redundant
members:

| Member | Marginal output bytes |
| --- | ---: |
| `MAX_ARTEFACT_BYTES` | 1,466 |
| `MAX_STORE_BYTES` | 1,452 |
| `RETENTION_MS` | 1,440 |
| `WorkContextErrorCode` | 1,561 |
| `WorkContextError` | 1,664 |
| `WorkContextError.constructor` | 937 |

Together they consume 8,520 marginal bytes (the state grows another 132 bytes
from omission accounting between the recorded additions), despite only 502
new source-content bytes. The constructor source is contained by the already
selected class source, yet its separate node, item, ownership record, extent,
and source locator still add 937 envelope bytes.

The first explicit-pair target bundle adds 1,457 unique evidence bytes but
4,539 output bytes. Its five new serialized source objects account for 4,056 B
(89.4% of the bundle): 1,485 B of source content, 1,329 B of `source_ref`
strings, and 1,242 B of other repeated source metadata. The remaining 483 B is
relationship/framing data. This is real representation pressure, but removing
proof or locators is not the repair: the proof is the supported identity chain
and is required to keep the relationship trustworthy.

The atomic candidate rejection is therefore caused by four established facts:

1. extraction and barrel resolution succeeded;
2. complete proof is available;
3. ownership nodes and arbitrary same-file members are scheduled before
   semantic proof, and ownership-lifted file nodes join the same-depth semantic
   scheduler;
4. full proof has a 3.1x envelope-to-new-evidence footprint in the clean
   explicit-pair attempt, so the fixed output limit rejects the late bundle.

`output_budget` is the immediate rejection, not a sufficient causal
explanation. Raising the limit to 32,768 B delivers the capture and explicit
pair edges, but the broad binding query still reaches 32,630 B before its 44th
target attempt and proposes a 35,413 B candidate. Selection simply fills the
larger envelope first.

## Counterfactual and repair boundary

The local counterfactual retains anchor source, native file nodes, ownership
associations, semantic families, complete proof, and the normal 16,384-byte
limit. It only prevents ownership-lifted nodes from recursively expanding
before anchor semantics.

| Request | Baseline target | Counterfactual target | Candidate at target |
| --- | --- | --- | ---: |
| capture query | omitted | delivered | 15,255 B |
| explicit pair | omitted | delivered | 9,639 B |
| broad binding query | omitted | omitted | 17,921 B |

A narrower counterfactual that only removes file-to-sibling declaration lifts
delivers the explicit pair at 9,767 B with 6,617 B headroom. It does not repair
the capture query because the ownership-lifted `service.ts` file is still
expanded at the anchor's depth and its import edges pack before the target.
This is why the implementation should stage ownership-driven expansion rather
than delete ownership or merely increase the output limit.

The minimal implementation boundary is:

1. Pack each selected symbol anchor, its definition, its native file node, and
   the `indexed_file` ownership association as today.
2. Schedule direct semantic neighbors of selected anchors before traversing
   ownership-lifted file/package/module/crate nodes or selecting their members.
3. Within that first semantic stage, prioritize an edge joining two explicit
   anchors. Keep the existing deterministic family/direction queues for other
   peers.
4. Spend remaining node/item/evidence/output capacity on native owner traversal
   and representative members. Preserve member expansion when the user selected
   an exact file anchor.

The change must not special-case these symbol names, weaken atomic proof, omit
TypeScript controls, or claim exhaustive impact from `WorkContextBinding`.

## Regression constraints

The repair should have a compact synthetic TypeScript fixture with a consumer
type, a public barrel, the defining type, and enough unrelated declarations to
recreate the pressure. Assert that the capture/options query and explicit pair
both return the exact `uses_type/import-resolved` identity with complete import,
re-export, definition, and control proof under 16,384 B. The explicit-pair test
must fail under the old eager ordering, so a small two-function fixture is not
sufficient.

Preserve these existing policy behaviors:

- exact file anchors still return representative members;
- native file/package/crate/module ownership and its proved imports remain
  available after direct anchor semantics;
- both traversal directions and all four relationship families remain
  interleaved after the reserved anchor-semantic stage;
- insertion order does not change the packet;
- missing proof still produces `proof_unavailable` rather than an edge.

Use the frozen positive cases as deterministic regression fixtures, without a
new provider batch:

- Browser: a `runBrowserCli` anchor must retain the forward exact
  `runBrowserCli -> browserCliUsage` call and the reverse import-resolved
  `bin/anvil.ts::main -> runBrowserCli` call, including the browser barrel proof
  from `src/browser/index.ts`. This catches starvation of reverse calls when
  anchor semantics are staged.
- Renderer: a `renderActiveTask` anchor must retain the forward
  `renderActiveTask -> truncateText` call and the reverse
  `renderContinuityFrame -> renderActiveTask` call. This catches a repair that
  over-prioritizes one traversal direction or type edges over call peers.

Relevant current tests to preserve or extend are
`tests/test_retrieval.py::test_fixed_policy_delivers_bidirectional_calls_types_and_native_imports`,
`test_relation_between_two_explicit_anchors_is_still_delivered`,
`test_family_rounds_interleave_two_high_fanout_anchors`,
`test_insertion_order_does_not_change_semantic_packet`, and
`test_native_go_package_endpoint_keeps_import_and_package_control_proof`.
