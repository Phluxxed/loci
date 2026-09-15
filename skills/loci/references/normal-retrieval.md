# Normal retrieval results

`loci_retrieve(repo, query="", seed_ids=None)` is the normal source operation.
At least one query or exact node ID is required. A query equal to an indexed
relative path selects that file. Otherwise symbol metadata is ranked, with
bounded literal-source matching when metadata yields no anchor. Several
candidates are alternatives, not unique resolution.

A case-sensitive camel/Pascal-case or underscore identifier in a question gives
an identically named code declaration priority over prose matches. Duplicate
declarations remain alternatives. Plain-language document questions keep the
metadata ranking; this is not arbitrary-name or runtime symbol resolution.

The `normal-graph-v1` policy always inspects supported calls, types, value
references and imports in both directions. It traverses up to two semantic
hops, interleaves relationship families and returns source with proved edges.
Direct relationships of selected anchors precede ownership expansion. Shared
declarations connected to two selected anchors by supported type edges receive
priority over incidental calls; only those type edges get this priority.
Every delivered edge still requires its complete static proof.
The same snapshot and request produce the same selection. The live schema
publishes the fixed work, source and complete-result limits.

Read these fields together:

- `anchors` identifies the starting candidates; `selection` reports matching
  scope and candidate omissions.
- `nodes` holds exact identities; `items` carries selected source and whether
  the whole owning extent is present. Use an item's `source_ref` for expansion.
- `relationships` retains the native edge direction, traversal direction,
  resolution qualification and IDs of its complete proof source.
- `ownership` connects declarations to their indexed file/package/module/crate
  context. It is separate from semantic relationships.
- `sources` holds exact byte/line spans and hashes. A preview can be exact bytes
  while still being an incomplete declaration; inspect `items.complete`.
- `scope`, `status` and `omissions` bound conclusions. Partial results may still
  contain useful evidence; no result is exhaustive runtime impact.
- `usage` distinguishes examined nodes, considered/traversed edges, delivered
  relationships, unique source bytes and the complete MCP-result bytes.

`loci_read(repo, source_ref)` pages one hash-bound source extent. Its returned
`next_source_ref` continues that extent; `complete=true` ends it. It discovers
no other source. References are exact locators, not credentials or proof of
prior issuance. Changed source returns `SOURCE_STALE` instead of applying old
offsets to the new file.

Re-anchor a returned identity to request further graph context under the same
policy. This is a new bounded retrieval, not a guarantee to enumerate omitted
neighbors. Use operator diagnostics for an explicit investigation of graph
storage, resolver records or index health.
