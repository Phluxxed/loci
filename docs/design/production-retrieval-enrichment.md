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

Enabled output remains `normal-graph-v1`, unchanged. Disabled output retains that
pipeline policy and the same response shape, with `scope.relationships` set to
`"disabled"` rather than `"known_static_relationships"`. The typed response model
accepts both values. No omission or partial status is manufactured merely because
enrichment is disabled.

The marker is set **after** common baseline packing so it cannot change anchor
admission. Disabled usage counts examined anchors, with zero considered/traversed
edges and zero delivered relationships. Final byte/token accounting uses the
same finalizer. All fixed limits, including hop and source-preview limits, remain
unchanged; no freed budget is spent on additional source selection. Source refs
are persisted by the same packer and expanded by the same `service.read` path.

Runtime/evaluation code can call `service.retrieve(..., graph_enrichment=False)`
or bind that keyword in its trusted service adapter. It must not forward an
agent-provided graph control. This seam does not itself change any experiment,
MCP configuration, instructions, or runtime launcher.
