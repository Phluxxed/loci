# Normal retrieval results

The MCP result's `structuredContent` holds the packet. Successful `content` is
empty. Follow the skill's Code Mode save-and-display procedure so a compact
receipt does not discard source needed later.

`loci_retrieve(repo, query="", seed_ids=None)` is the `source-context-v1`
operation. Supply a nonblank query or up to five exact node IDs. An indexed
relative file path or exact ID selects directly. Other questions rank bounded
declaration and file candidates. Matching source literals compete before weak
metadata matches; a selected literal excerpt includes the matching span even
when it occurs late in a large definition. Several candidates are alternatives,
not unique resolution.

A case-sensitive camel/Pascal-case or underscore identifier in a question gives
an identically named code declaration priority over prose matches. Duplicate
declarations remain alternatives. Plain-language document questions keep their
metadata ranking; selection does not infer runtime symbol identity.

The native TypeScript/TSX parser indexes simple initialized top-level `const`
identifiers regardless of case, including exported declarations. Their exact
declaration spans use the existing constant kind and file ownership. This adds
no inferred runtime schema meaning. The process-only parser fallback retains
its prior uppercase-name filter; lower-case mutable, nested, destructured and
malformed declarations receive no new constant identity.

Read these fields together:

- `anchors` identifies starting candidates; `selection` reports match scope and
  candidate omissions.
- `nodes` holds indexed identities. `items` identifies selected source and
  whether its complete owning extent was delivered. Use `items[].source_ref`
  for exact continuation.
- `sources` holds exact UTF-8 byte and line spans with hashes. A useful excerpt
  is still incomplete when `items[].complete=false`.
- `ownership`, when present, records indexed file membership. File identities
  remain distinct from declaration identities.
- `relationships=[]` and `scope.relationships="not_selected"` mean normal
  retrieval did not inspect dependencies. They do not establish independence.
- `scope`, `status` and `omissions` bound conclusions. Partial results can
  still contain useful source; source coverage may be complete, partial or
  unknown independently of selection.
- `usage` and `limits` report fixed work and byte bounds. There is no normal
  caller control for traversal or relationship expansion.

The fixed selection caps are three inferred anchors, five explicit anchors,
twelve items, 64 examined nodes and 256 literal matches. Literal lookup scans
at most 4096 files or 32 MiB. Source evidence fits 8192 unique bytes and the
complete MCP result fits 16384 bytes. The full selected definition is delivered
when it fits both budgets. Otherwise Loci delivers a useful UTF-8 excerpt and
an exact short handle for its owning extent. The same snapshot and request
produce the same bounded selection.

`loci_read(repo, source_ref)` pages one hash-bound extent. Pass the returned
short handle unchanged; follow `next_source_ref` until `complete=true`. Loci
retains the exact repository, path, content hash and byte extent in its bounded
per-repository cache. Handles survive server restarts while retained there.
An unknown, evicted or cross-repository handle requires fresh retrieval;
changed source returns `SOURCE_STALE` rather than applying old offsets. Reads
preserve exact contained UTF-8 bytes. Legacy encoded locators remain readable
for compatibility. A reference locates source; it is not an authorization
credential or proof that an earlier caller received the source.

Source retrieval and reads refresh declarations and file inventory without
validating or materializing a graph. The stored index file may still be parsed
as a whole. For an operator-selected graph investigation, use the separate
diagnostic surface described in [graph-navigation.md](graph-navigation.md).
After source changes, old graph data is unavailable until an explicit graph
refresh rebuilds it.
