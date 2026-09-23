# Internal production graph-enrichment seam

`service.retrieve(..., graph_enrichment=True)` forwards its keyword-only control
through `retrieve_context(..., graph_enrichment=True)`. Both default to enabled.
Trusted process code can bind either value; the normal `loci_retrieve` MCP input
schema and instructions are unchanged and do not accept this argument. No
benchmark implementation is needed.

The shared production pipeline is:

1. Load/validate the same index and graph store and compute query coverage.
2. `_prepare_context`: validate the request, construct the same `RetrievalSource`,
   select anchors, and initialize the same `RetrievalPacker` and selection metadata.
3. `_pack_anchor_sources`: pack the existing `_anchor_addition` for every anchor,
   with the same atomic admission, previews, omissions, budgets and source refs.
4. If disabled, finish that baseline packet. Otherwise, run the existing
   relationship traversal and ownership expansion, then finish with the same
   packer.

## Baseline ownership

Anchor packing retains the anchor's indexed file node and `indexed_file`
ownership identity, when available. It does **not** hydrate the owner's source
or select representative members. An exact file anchor still has its own source
preview, but its representative members are only selected during enrichment.
Graph-off therefore is not an ownership-free policy: it is the natural stopping
point before graph-driven expansion. Graph state and source-record indexes are
still loaded in both modes; graph-off performs no relationship traversal, proof
hydration, signature/bridge selection, unresolved-relation counting or ownership
expansion.

## Output and budgets

Enabled output remains `normal-graph-v1`, unchanged. Both modes retain the same
response shape and `scope.relationships = "known_static_relationships"`.
**This field describes the evidence domain of any returned relationships, not
whether traversal ran or relationships were searched for.** It is not execution
metadata: an empty relationship list makes no discovery or absence claim, in
either mode. `exhaustive` remains false; any delivered relationship must still
satisfy the same static-evidence/proof contract. This meaning is explicit in the
typed output schema. The former `"disabled"` execution-state value is rejected.
The `policy` field identifies the fixed pipeline, not its enabled stages.

No arm marker, omission or partial status is manufactured because enrichment is
disabled. Graph-off exposes only the natural baseline packet and truthful usage:
examined anchors, zero considered/traversed edges and zero delivered relationships.
These counts are not an arm label; graph-on can also return no relationships.
Final byte/token accounting uses the same finalizer. All fixed limits, including
hop and source-preview limits, remain unchanged; no freed budget is spent on
additional source selection. Source refs are persisted by the same packer and
expanded by the same `service.read` path.

## Trusted execution state, outside the packet

`service.RetrievalRuntime` is an immutable process-bound configuration. Its
`graph_enrichment` field defaults to true; its `retrieve` method delegates to the
same production `service.retrieve` without accepting an arm override:

```python
runtime = service.RetrievalRuntime(graph_enrichment=False)
packet = runtime.retrieve(repo, query)
receipt_metadata = {"graph_enrichment": runtime.graph_enrichment}
```

Trusted execution/evaluation code records `receipt_metadata` separately and
forwards **only** `packet` to the agent. The binding retains the configured state
even when both modes produce identical empty packets or a request fails. No
inference from relationship counts is needed. Direct trusted callers of
`service.retrieve`/`retrieve_context` can still use the existing boolean seam and
retain that configuration themselves.

There is no packet-masking/projection step and no execution metadata attached to
MCP `content`, `structuredContent`, or `_meta`. The existing MCP adapter forwards
the already model-safe packet unchanged. The input schema stays `repo`, `query`,
`seed_ids`; it does not expose runtime configuration. Runtime bindings/receipts
must not be serialized into tool results. This patch does not wire an experiment,
change MCP instructions/configuration, or add a runtime launcher.
