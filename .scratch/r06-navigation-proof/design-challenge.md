# R0.6 bounded architectural challenge

Assignment: design-challenge, Astra/high/none. Original scope was this report;
the lead subsequently authorized `delivery-audit.json` and `delivery_audit.py`
for exact retained-artifact diagnosis. No product changes, measurement jobs,
commits, ambient store access, or child agents. Contribution: challenge the proof follow-up before implementation and
causally account for the 20 supported but undelivered R0.5 links. Findings below
come from current source inspection and retained artifacts, not new measurements.

## Recommendation

Use exact endpoint reanchoring with the existing complete-proof packer first.
Keep graph-free path acquisition independent of this optional semantic request.
Do not introduce session-linked proof paging for this experiment: the retained
losses do not yet show that an individual complete proof cannot fit an otherwise
empty packet. Reanchoring is an operational hypothesis, not a claim that four
follow-ups recover every supported relationship.

A four-call, stable-order queue of previously returned endpoint IDs is a
reasonable bounded consumer heuristic. Freeze it before scoring. Deduplicate
IDs, skip identities already focused by the new proof policy, preserve request
provenance, and record
which eligible IDs remained beyond the call/byte limit. IDs from observer
indexes, evaluator-required links, or proof-failure diagnostics cannot enter the
consumer queue. Observed declaration text can motivate a new lexical question;
it does not by itself mint an exact node identity or establish binding.

## Retained evidence: all 20 losses accounted for

Inspected `src/loci/demand_semantics.py`, `benchmarks/architecture.py`,
`benchmarks/architecture_cases.py`, and artifacts below
`.scratch/r05-demand-semantics/results/full-source-demand/artifacts/`.
For each variant-1 suite-0/1 capability row with an available but undelivered
required link, I joined its exact native edge identity to the case's retained
`case-indexes/*.json.gz`, semantic packet, and `worker.json` semantic work.
I reconstructed the packer's two separate forward/reverse two-hop frontiers
from delivered anchor IDs and matched per-edge `proof_failures`. This is offline
evaluator diagnosis; it must not become runtime target selection.

| Case | Missing required link(s), using evaluator context labels only for diagnosis | Cause |
| --- | --- | --- |
| local_alias_chain | first → payload | selection |
| imported_alias_chain | first → payload | selection |
| local_heritage | child → contract | selection |
| imported_heritage | child → contract | selection |
| anvil_temporal_arguments | view → views | selection |
| anvil_retrieval_limits | entry → input; input → omission, stop, reporting, diagnostic | packet capacity (5) |
| anvil_renderer_result_contract | entry → input; input → project | packet capacity (2) |
| javascript_known_call_impact | make → add | packet capacity |
| rust_authored_trait_contract | render → format | packet capacity |
| rust_authored_trait_contract | receipt → id; format_impl → format, receipt; render_impl → render, receipt | selection (5) |
| rust_known_call_impact | caller → config | selection |

Totals: **11 selection losses, 9 packet-capacity losses, 0 closure losses or
unexplained losses within these 20**. Selection means the exact supported edge
is outside the packer's eligible set, not simply lower ranked. All nine capacity
losses exactly match an observer failure with `proof exceeds packet budget`.
The included read-only regeneration script verified the same 11/9 split in
both retained repetitions. This is a replay of historical artifacts, not new
measurement, and does not diagnose the separate 25 Python/Go support gaps.

Concrete checks against misleading aggregate explanations:

- `local_alias_chain`: 3 native required links, 2 delivered; 138 unique evidence
  bytes, 9,433 envelope bytes; no omissions. The consumer sees `processOrder`,
  `Second`, and `First` identities. The third edge is beyond the selected frontier.
- `imported_alias_chain`: equivalent 3/2 gap with 180 evidence bytes and 10,048
  envelope bytes, also no omissions.
- `anvil_temporal_arguments`: aggregate proof failures exist, but its one missing
  required link is not one of them. It is excluded by selection.
- `rust_known_call_impact`: caller → Config requires reverse traversal from the
  initial target followed by forward traversal from its caller. The policy walks
  forward and reverse independently, so this mixed-direction relation is absent
  from eligibility even though native support exists.
- `anvil_retrieval_limits`: only 3,256 evidence bytes have been accepted when the
  response is already 15,483 bytes. Thus packet rejection cannot automatically
  be called exhaustion of the 8KiB evidence allowance.

The native packer reserves 512 bytes below the final 16KiB envelope limit and
emits anchor/outward source previews before relationship proofs. Full endpoint
declarations, support and control files can overlap or duplicate source payload
on the wire even where the evidence-byte union is small. One generic rejection
string currently combines the evidence and envelope tests.

## Causal separation and the smallest diagnostic additions

Use per-edge stages: native support absent; present but proof-gated by incomplete
closure; present but traversal-ineligible; selected but support unavailable;
selected but evidence cap exceeded; selected but envelope cap exceeded; delivered.
Keep native edge existence distinct from proof completeness. A general closure
omission does not establish that a particular missing link was lost to closure.

For each budget rejection, record attempted evidence-union bytes and serialized
full-envelope bytes before rollback, the governing fixed caps, and accepted
packet size before the attempted claim. This distinguishes the two capacity
constraints without weakening either. The next useful counterfactual is whether
that same edge's complete proof fits an empty/minimal packet under fixed caps.
An edge that fits alone but loses after previews or earlier claims has a packing
competition problem; an edge that fails alone has an indivisible proof-size
problem under this contract. Neither implies the source was unavailable.

Exact-focus support must change actual anchor IDs and ordering. `anchor_file`
and a symbol-name query alone remain lexical and can select another same-named
symbol. Validate the exact ID belongs to the current admitted source/snapshot,
then fail explicitly on stale/absent focus instead of silently falling back.
Include focus identity and policy caps in any cache identity; a narrow cached
packet must not answer a wider or differently focused request accidentally.

A focus request that reruns extraction with different query/seeds may change the
native slice and its closure. Therefore the fixed-cap focused condition is **not
necessarily selection-only**. Compare slice memberships/input hashes and report
whether each newly delivered edge was already natively supported in the original
slice. For a pure selection/packing counterfactual, retain and repack exactly the
same slice offline. Avoid reconstructing a mixed native index from independent
slices if that would invent resolution combinations or discard an earlier
packet's supporting records; strict scoring needs each claim's actual provenance.

A 32KiB-evidence/64KiB-envelope variant is justified only as an explicit diagnostic
upper bound after fixed-cap focused failures. It changes two constraints jointly,
so name its effect combined packet capacity. Per-attempt byte telemetry may be
enough to avoid another variant. If separate causal effects are necessary, hold
one cap fixed while varying the other. Never label the larger-cap response an
ordinary baseline-budget success. Charge all optional calls, response bytes,
source bytes, repeated source, and admission overshoot to the same session ledger.

## Adopted implementation decision after consultation

The lead chose to retain the original native slice and prepacking state, then
reuse that slice for exact visible-node focus with proof-first packing. The
original source inventory is revalidated before and after each request. This
removes the resolver-rerun confound described above and is adopted for the
bounded experiment. Deep-copy the packing work state so focus omissions do not
mutate baseline observations. Charge retained raw/native state and process peak
memory explicitly. No new resolver work may be implied by this condition.

The frozen candidate uses up to four visible identities, original anchors then
related identities in stable encounter order. Refocusing an original anchor is
legitimate here because proof-first packing differs from the baseline policy.
That one call spends part of the four-call limit and may reduce downstream
coverage; report it. Test ordinary 8KiB/16KiB fixed limits first, then the explicitly
diagnostic 32KiB/64KiB condition. The larger variant identifies combined packet
capacity, while per-attempt sizes can distinguish the active constraint. This
bounded schedule cannot establish universal sufficiency or insufficiency of
reanchoring or paging.

## Consumer contract and paging boundary

Current responses expose identities through `anchors`, `nodes`, `items`, and
relationship endpoints. Omission counts and `selection.omitted_candidates` do
not identify omitted candidates. `source_ref` is an authenticated extent locator,
not an omitted-edge continuation. `read()` pages source but asserts no new
relationship. The current scheduler asks exactly one semantic question in slot2;
subsequent ordinary lexical calls cannot claim undisclosed semantic edges merely
because both endpoint source bodies were acquired.

Strict proof validation must still require the native resolved relationship,
valid current endpoint identities, exact supporting bytes/hashes, resolution
controls, and existing conservative ambiguity/closure/configuration semantics.
The existing session-source-union score is separate from packet proof and still
requires an actually delivered claim. It must not turn observer membership or
source co-occurrence into a relationship.

Session-linked paging would need an explicit incomplete claim, snapshot-bound
proof identity, references to all required support pages, exact progress and
stale handling, and a consumer that withholds the complete claim until validation
succeeds. That is a larger contract change. Defer it unless fixed-cap empty-packet
feasibility shows indivisible proofs really need it and a further change is
within the authorized outcome. Failure of four scheduled focuses alone does not
justify paging: the missing endpoint might be fifth in the queue or never exposed.

## Minimum acceptance and negative checks

1. Freeze and replay the focus queue using only prior consumer packets; changing
   evaluator gold must not change requests. Record source packet and identity for
   each follow-up. Verify max4, deduplication and shared admission/overshoot.
2. Prove exact-ID behavior with same-name declarations: the specified returned
   identity wins, and unknown/stale IDs fail explicitly. Verify cache isolation.
3. Pass unchanged strict proof checks plus packet-shape/full-envelope accounting
   on every new claimed edge. Preserve unsupported, unresolved, ambiguous,
   inaccessible, external and Rust `declared_possible` qualifications.
4. Include one tiny third-hop case and the reverse-then-forward case to test
   selection; one genuine capacity rejection to test honest partial output; and
   one ambiguity case to ensure focusing does not manufacture certainty.
5. Report original supported links, additional strictly delivered links, still
   undelivered links by causal stage, new optional cost, and stop reasons. Keep
   source acquisition, semantic proof and task correctness separate.

A valid negative outcome is that bounded gold-blind focuses recover no extra
proof, recover only some links, or remain constrained by the queue/packet caps.
That completes this bounded question when evidence is sufficient; it does not
require production changes, V2, a live-model campaign, or a new protocol.
