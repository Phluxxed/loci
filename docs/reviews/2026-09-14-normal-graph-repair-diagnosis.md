# Normal graph retrieval: token and delivery diagnosis

**W1.8.4.1 is complete.** The token increase reconciles to the original provider
records. The missing binding relationship is a selection-order defect, and
some reported truncation is an observer limitation. W1.8.4.2 repairs selection; W1.8.4.3 corrects the delivery readout.
The repaired live path remains pending a host restart under W1.8.4.4. No new provider attempts were run.

## The token increase is real

Eight retained binding/checkpoint intervals reconcile per-response usage,
cumulative deltas, frozen totals, operation counts, output bytes and native
interval hashes. For binding, median provider responses grew from 6.5 to 12.5;
input per response also grew. Total input was 249,298 before and 678,996.5 after
(2.7236x). Uncached input rose from 36,946 to 64,212.5 (1.7380x), while visible tool
output grew 1.2818x. These are two attempts per condition, not a population or
billing estimate.

The high binding run used 16 provider responses. Its later responses 8–16 contain
676,990 input tokens, or 73.19% of its total. That measures repeated processing;
it is not an estimate of savings from deleting those responses, which could
also delete required evidence. The checkpoint pair has fewer median responses
but larger contexts; run 22's 26 MCP calls are a separate fanout pattern.

The [per-round report](../../.scratch/deterministic-graph-retrieval/diagnosis/token-diagnosis.md)
and [normalized accounting](../../.scratch/deterministic-graph-retrieval/diagnosis/token-results.json)
preserve all eight trajectories and limitations. Worker-proposed new call/token
ceilings are diagnostic suggestions only; the existing acceptance thresholds
were not changed.

## Valid proof is crowded out

The fixed Anvil index contains the exact `CaptureCommandResultOptions →
WorkContextBinding` type relationship and its complete import/barrel/definition/
control proof. Each of the three retained primary requests attempts that edge.
Extraction and resolution succeeded.

The pre-repair traversal packed ownership context before anchor semantics. In the
explicit-pair request, two anchors occupy 5,062 bytes. Six unrelated or redundant
file members then add 8,520 bytes, before the first semantic edge. The target
addition reaches 18,292 bytes and is correctly rejected by the 16,384-byte result
ceiling. Removing proof or raising that ceiling would miss the actual ordering
problem.

A deterministic engineering counterfactual defers ownership-driven expansion.
The options query then delivers the edge at 15,255 bytes and the explicit pair at
9,639 bytes, with complete proof. Removing only sibling declarations is
insufficient for the options query because the owner file's import traversal
still runs first. The broad binding-only query remains bounded and does not
promise one specific consumer among 36 eligible neighbors.

The selected repair preserves anchor definitions, native owner identities and
ownership associations, gives direct anchor semantic proof the first stage,
then spends remaining capacity on owner traversal. Explicit anchor-to-anchor
relationships receive priority. Existing file-anchor behavior, family/direction
fairness, work ceilings and atomic proof remain required. The
[selection report](../../.scratch/deterministic-graph-retrieval/diagnosis/selection-report.md)
and [probe](../../.scratch/deterministic-graph-retrieval/diagnosis/selection-probe.py)
retain the causal trace, byte accounting and regression constraints. The diagnosis
ran against pre-repair commit `9960163`; reproducing that failure requires that
source revision. The probe imports local code, so running it after this repair
measures the repaired policy. Original probe outputs remain unchanged.

## Correcting the earlier delivery interpretation

The frozen observer cannot parse several complete JSON values joined into one
text block. It also applies a truncation warning from any block to otherwise
unmatched calls throughout the turn. Thus `unknown_truncated` is not evidence
that every labelled packet was clipped.

Inspection of the exact retained JSON lines establishes:

- Run 17 has one clipped middle retrieval; other labelled results remain intact.
- Run 21 has five intact retrievals, one clipped retrieval and one intact read.
- Run 20 first printed the empty `content` field and discarded the structured
  body, then repeated the request. Its identical native results remain
  ambiguous at the invocation level because the host does not record a trusted
  nested-to-outer call identity.

The earlier statement that all six run 21 retrievals were truncated was too
strong. The [delivery diagnosis](../../.scratch/deterministic-graph-retrieval/diagnosis/delivery-boundary-diagnosis.md)
records the exact native/output references. The frozen adapter, observations,
answer reviews, scores and negative value verdict remain historical artifacts.
A separate versioned adapter recovers complete JSON-line delivery without
promoting fragments or inventing invocation provenance. This does not regrade
the baseline or demonstrate improved ordinary correctness or token consumption.

Loci respects its per-result byte ceiling; it cannot control arbitrary outer
aggregation or a caller that discards its return value. Full JSON duplication
into compatibility text would displace proof. A 63-byte marker would expose an
empty-field mistake but would not recover the discarded result. Neither is
selected as the repair. Repeated long locators consume about 3.9–5.35 KB in the
measured 16 KB packets, but shortening them alone could simply let the packer
fill the same ceiling with more data; no locator/schema redesign is selected.

## Required follow-through

The [repair contract](../../.scratch/deterministic-graph-retrieval/repair-contract.md)
defines source scopes and deterministic regression checks for W1.8.4.2/.3.
W1.8.4.4 must verify integrated source and actual-host behavior, retaining any
restart limitation. Existing strict-answer and workflow-cost failures remain
open. A future provider comparison requires a separately selected bounded
campaign and pre-outcome freeze; none is implied by this diagnosis or repair.

## Implemented repair and activation check

W1.8.4.2 now stages selected anchors' direct semantic relationships before
ownership expansion. Explicit-anchor pairs receive priority before the neighbor
cut. The fixed Anvil replay delivers the complete binding proof for the options
query (16,091 output bytes) and explicit pair (16,019 bytes), within the original
16,384-byte limit. Browser caller/barrel proof and both renderer call directions
remain intact. Broad binding retrieval still does not promise one consumer.
See the [selection repair receipt](../../.scratch/deterministic-graph-retrieval/diagnosis/selection-repair-report.md).

W1.8.4.3 adds a supplementary exact JSON delivery observer. It preserves frozen
judgments and records original block/line/byte provenance, local clipping and
ambiguous repeated invocations. It corrects our evidence readout; it does not
change a caller that discards results or a host's aggregate output cap. See the
[delivery correction receipt](../../.scratch/deterministic-graph-retrieval/diagnosis/delivery-supplement-report.md).

Primary source review accepted the selection change. Sixteen retrieval tests,
47 normal MCP/server tests and nine additional normal acceptance tests passed.
Delivery observer checks and the retained matrix are recorded in its receipt.
All 45 frozen inputs still match their recorded hashes.

The actual-host options request returned the exact pre-repair structured result
from original primary MCP line 5297: 16,373 bytes, valid source spans, three
relationships and no binding edge. This session's long-lived Loci server has
not loaded the repair. The [activation receipt](../../.scratch/deterministic-graph-retrieval/diagnosis/repair-host-activation-check.json)
preserves that failed activation check; no standalone process replaces it.
Next is W1.8.4.4 after restarting the host. Ordinary answer/cost acceptance stays
open; these deterministic checks establish neither token savings nor benefit.
