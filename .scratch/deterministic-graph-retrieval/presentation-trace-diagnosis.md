# W1.8.4.4.9.1 retained presentation-trace diagnosis

## Disposition

One v3 retrieval was repeated solely to recover a result that the first outer
program had discarded at presentation time. The normal Loci call itself
succeeded and returned the full authoritative packet in `structuredContent`;
the caller selected only `content`, which was `[]`, and emitted an empty body.

The smallest effective correction belongs in the normal-use skill/contract:
show and require success decoding from `structuredContent` on the first call,
store that value before presentation, and emit it once. No Loci product-code
change is warranted for this retained behavior. A marker in `content` would
only make the mistake visible, and duplicating the proof as text would consume
the bounded result envelope or displace evidence. A content-only projection
would be a separately versioned interface decision, not a repair to
`normal-graph-v1`.

## Exact retained provenance

The behavior occurs only in `binding-repair-v3-02` (`t21`), whose inventory has
10 outer rounds. The two relevant entries are the fifth and sixth rounds
(one-based):

| Stage | Outer request/output | Outer call | Native event | Exact request | Projection and visible result |
| --- | --- | --- | --- | --- | --- |
| Initial retrieval | lines 43/46 | `call_ZRVyUfjsLpNZikXvJVnVSQxH` | line 45, `exec-612e81aa-9c1a-4785-9211-7cdc6f935530` | `loci_retrieve(repo="/tmp/anvil-source-tasks-20260914/t21", query="captureCommandResult")` | `text(r.content.map(x=>x.text||"").join("\n"))`; native `content=[]`, so body is 0 bytes, SHA-256 `e3b0c442...b855` |
| Recovery retrieval | lines 50/53 | `call_ez9wmYErBFE9acAlhgwOxziu` | line 52, `exec-b225fc7c-e115-46b7-adf3-167cadc0fd3a` | same repo, tool, and query | `text(JSON.stringify(r.structuredContent ?? r))`; body is the complete 16,217-byte structured packet, SHA-256 `88b5219f...505c` |

Both native calls completed successfully with `isError=false`, `content=[]`,
and the same full `structuredContent`: schema 1, policy `normal-graph-v1`,
snapshot `2847c266...cfe50`, partial coverage, one inferred anchor, five items,
six relationships, and fifteen source records. Their complete canonical MCP
results are byte-identical: 16,268 bytes, SHA-256
`50340b0a...98265`. The second call did not refine the query, change the
snapshot, or return new graph evidence.

The retained local counterfactual is exact: compactly serializing native line
45's `structuredContent` equals the visible body at output line 53 byte for
byte. Therefore the first outer program could have presented the observed
packet without issuing native line 52.

`binding-repair-v3-01` is the control for this particular seam: its first
retrieve emits `JSON.stringify(r.structuredContent ?? r.content)` and does not
repeat that same request. It does not isolate a population effect, but it shows
that the normal envelope was usable by the documented Code Mode host in the
same campaign.

## Mechanism, inference, and attributable excess

Observed mechanism:

1. The first native Loci result contains the full structured value.
2. The outer program reads only `r.content`; because that list is empty, its
   output body is exactly empty.
3. The immediately following outer program repeats the identical native
   request and changes only the projection to `structuredContent`.
4. The recovered value is exactly equal to either native result.

This establishes one avoidable presentation-recovery Loci call and one
presentation-recovery outer round. It is not a second benchmark attempt;
`graph-delivery-review.json` correctly records `extra_attempt=false`.

The causal statement that the empty body prompted the repeat is a strong
trace inference, not exposed model reasoning: the intervening reasoning is
encrypted. The unchanged query and result plus the projection-only correction
make the recovery purpose clear, but the trace cannot prove the agent's private
decision process or how later rounds would have unfolded under a changed
instruction.

Attribution limits remain frozen. Delivery-v4 classifies both identical native
calls `ambiguous_exact`, because the one visible packet at output line 53 can
match either call. That status must not be promoted to per-call `full_exact`.
There is no clipping evidence, and exact packet visibility does not prove model
reliance. The separate nested-value checks and every frozen observation,
review, score, and classification remain unchanged.

This diagnosis makes no token, elapsed-time, or whole-run savings claim. The
retained counterfactual proves only that one structured packet could have been
presented on the first call and that the identical recovery call/outer round
was unnecessary for obtaining that packet.

## Smallest owning-surface correction

Add one normal success recipe beside the Code Mode exact-name workflow in the
installed Loci skill and `normal-retrieval.md`. The operative shape is:

```javascript
const r = await tools.mcp__loci__loci_retrieve({repo, query});
const packet = r.structuredContent ?? r;
store("loci.normal.packet", packet);
text(JSON.stringify(packet));
```

The guidance should also say:

- inspect `packet.error` as a failure before consuming success fields;
- use the stored packet's issued `source_ref` unchanged for `loci_read`;
- do not repeat an unchanged request merely because `content` is empty; and
- emit each near-limit packet separately rather than assuming an arbitrary
  outer aggregation will remain intact.

The first three bullets address this retained repeat. The final bullet is an
adjacent existing delivery constraint, not causal to the blank v3 output.

Primary's independent source inspection locates the deliberate envelope at
`src/loci/mcp_server.py:751` (`content=[]`,
`structured_content=payload`). Before any product-code proposal, the precise
boundary questions are whether that constructor is shared by retrieve and
read, whether `usage.output_bytes` budgets the complete MCP envelope, and what
evidence a second text representation would evict at the ceiling. The retained
trace supplies no need to change that constructor. The current skill and
`normal-retrieval.md` describe result fields and errors but contain no complete
Code Mode success-decoding/store-before-print example; that is the owning gap.

## Direct local acceptance scenario

Use a deterministic stub for `loci_retrieve` that increments a call counter and
returns `{content: [], structuredContent: {schema_version: 1, status: "partial",
sentinel: "present"}, isError: false}`. Execute the published recipe once and
require all of the following:

1. the call counter is exactly one;
2. `loci.normal.packet` equals the stub's `structuredContent` exactly;
3. the emitted text is non-empty JSON and parses to that same value; and
4. no fallback repeats the retrieve because `content` is empty.

Then run the same assertion through the local normal Loci transport with one
fixed query: the native envelope may retain `content=[]`, but the outer output
must equal its `structuredContent`, and the captured trace must contain exactly
one matching native request. This is a local presentation check, not a provider
trial. Keep the v3 artifacts frozen and do not infer provider-token savings
from either check.
