# Tool contracts and bounded evidence

## Contents

- Core response envelopes
- Compact exploration output
- Coverage, pagination, and empty-result rules
- Graph health and store-health contracts

## Core response envelopes

`loci_outline` returns grouped files and symbols:

```json
{"files":[{"file":"src/foo.py","symbols":[{"id":"...","name":"...","kind":"function","line":1,"end_line":10,"signature":"...","summary":""}]}]}
```

`loci_get` returns exact source for requested symbols:

```json
{"symbols":[{"id":"...","source":"...","line":1,"end_line":10,"byte_offset":0,"byte_length":200,"signature":"...","kind":"function","language":"python"}]}
```

`selected_from_search_id` is optional. Supply it only when every requested
symbol was deliberately selected because of that exact search. Direct,
outline-driven, hydration, and mixed-purpose gets omit it. Unknown or
cross-repository lineage fails with `INVALID_SEARCH_LINEAGE` before retrieval
or selection telemetry is recorded.

`loci_search` returns ranked symbols, coverage, and an opaque selection id:

```json
{"symbols":[{"id":"...","name":"...","kind":"function","score":20.0,"signature":"...","summary":""}],"coverage":{"schema_version":1,"state":"partial","scope":"repository","source_scope":"indexed_supported_source","query_scope":"indexed_symbols","indexed_files":12,"excluded_paths":3,"exclusions":[{"reason":"ignored","paths":1,"samples":["local.py"],"omitted_samples":0},{"reason":"policy_excluded","paths":2,"samples":[".git","build"],"omitted_samples":0}],"unknown_reason":null},"search_id":"opaque-id"}
```

`search_id` is non-null for a non-empty result envelope and null for an empty
search. It has no expiry. Loci resolves any declared selection rank from the
ordered symbols returned for that identifier; callers never supply rank.

`loci_search.file_paths` is an optional caller-supplied exact-file eligibility
allowlist. Omission or `null` searches the complete indexed repository; an empty
list makes no files eligible. Entries must be normalized repository-relative
POSIX paths, and the bounded list accepts at most 500 entries. Eligibility is
applied before scoring, sorting, search logging, and `limit`, while coverage
continues to describe the complete repository index. Invalid paths, values, or
list sizes return structured `INVALID_INPUT` errors. This is a generic search
scope; callers retain ownership of any domain meaning attached to the paths.

`loci_grep` returns matching lines with context and the same coverage shape:

```json
{"matches":[{"file":"...","line":42,"match":"...","context_before":[],"context_after":[]}],"coverage":{"schema_version":1,"state":"complete","scope":"repository","source_scope":"indexed_supported_source","query_scope":"indexed_source_text","indexed_files":12,"excluded_paths":0,"exclusions":[],"unknown_reason":null}}
```

Coverage is identical for empty and non-empty outcomes. `complete` means no
excluded paths; `partial` reports known ignored, policy-excluded,
sensitive/binary, or unsupported paths; `unknown` means a legacy index has not
recorded coverage. Samples are capped at 20 paths per reason and
`omitted_samples` reports the remainder. Never interpret an empty result as
absence outside its `query_scope`. The CLI preserves its existing bare-array
output for compatibility.

## Compact exploration output

`loci_explore` requires `repo` and `intent`. It returns `items`,
`relationships`, shared `sources`, `omissions`, `scope`, `limits` and `usage`.
Each item's `source_id` points to its definition or a containing source span;
`path` lists relationship IDs from its selected anchor. Relationship
`source_ids` point to complete authored and import/re-export proof source.
Source entries retain UTF-8 byte intervals, line bounds, full-file hashes and
exact text. Read `complete` on each item to detect clipped anchors.

`status="ok"` describes successful delivery of the selected packet;
`partial` reports uncertainty, missing source or a work/delivery bound;
`empty` contains no source items. Intentional pruning, cycles and alternative
paths are reported without alone making the result partial. Source coverage
retains the index's complete/partial/unknown state, while relationship scope
is always non-exhaustive.

`max_output_bytes` bounds the complete UTF-8 JSON MCP result, including its
content/structuredContent/isError framing, metadata, omissions and size fields.
It excludes the JSON-RPC request ID and transport envelope. `max_evidence_bytes`
separately bounds the union of delivered source byte intervals, including
definitions and supporting lines. `usage.output_bytes` is measured;
`estimated_tokens` is only the labelled `utf8_bytes_div_4` heuristic.
Use the tool's input schema for numeric limits. Unsupported intents return
`INVALID_INPUT` with the supported choices and `locate` fallback.

## Graph and health envelopes

`loci_graph_anchors` returns inferred or explicit starts without traversal or
answerability claims:

```json
{"schema_version":1,"repo":"...","question":"...","selection":"inferred|explicit","question_terms":[],"anchors":[{"node":{"id":"...","namespace":"loci","kind":"section","attributes":{"language":"markdown","file":"guide.md","line":1,"end_line":20}},"matched_symbol_id":"...","name":"Guide","score":12.3,"reason":{"kind":"inferred","matched_terms":["guide"],"match_scope":["file_basename"]}}],"counts":{"indexed_nodes":1,"eligible_units":1,"qualified_candidates":1,"collapsed_symbols":0,"returned_anchors":1,"omitted_candidates":0},"budget":{"requested_max_anchors":10,"effective_max_anchors":1},"diagnostics":[]}
```

`loci_graph_health` returns persisted extension status and diagnostics:

```json
{"schema_version":1,"repo":"...","status":"healthy|degraded","profiles":[],"counts":{"profiles":0,"node_overlays":0,"edges":0,"contributions":0,"diagnostics":0,"graph_file_nodes_indexed":0,"graph_swift_modules_indexed":0,"graph_go_packages_indexed":0,"graph_rust_crates_indexed":0,"graph_imports_indexed":0,"graph_imports_resolved":0,"graph_imports_unresolved":0,"graph_symbol_references_indexed":0,"graph_symbol_references_resolved":0,"graph_symbol_references_unresolved":0,"graph_symbol_references_resolved_by_basis":{},"graph_calls_indexed":0,"graph_calls_resolved":0,"graph_calls_unresolved":0,"graph_calls_resolved_by_basis":{}},"diagnostics":[]}
```

`loci_store_health` returns a bounded read-only store page:

```json
{"schema_version":1,"status":"healthy|unhealthy|incomplete","complete":true,"items":[{"cache_key":"...","repo":"/path/to/repo","symbols":12,"states":["stale","overlapping"],"reasons":[{"state":"stale","code":"SOURCE_CONTENT_CHANGED","details":{"added":[],"changed":["src/a.py"],"removed":[],"omitted":{"added":0,"changed":0,"removed":0}}},{"state":"overlapping","code":"REPOSITORY_ROOT_CONTAINS_INDEXED_ROOT","details":{"others":[{"cache_key":"...","repo":"/path/to/repo/sub"}],"omitted":0}}],"probe":{"status":"complete","index_bytes":4096,"repository_paths_scanned":20,"repository_bytes_scanned":8192}}],"counts":{"repositories":1,"returned":1,"healthy":0,"stale":1,"missing":0,"corrupt":0,"overlapping":1,"incomplete":0},"pagination":{"offset":0,"limit":100,"next_offset":null},"bounds":{"max_catalog_bytes":4194304,"max_index_bytes":67108864,"max_probe_paths":100000,"max_probe_bytes":536870912},"diagnostics":[]}
```

`states` preserves mixed findings. `healthy` is exclusive and appears only
after complete structural and freshness probes. Top-level `complete` is true
only when the response covers the whole catalog and every returned repository
probe completed. When an explicit catalog, index, path, or byte bound prevents
a conclusion, `probe.status` or a store-level diagnostic is `unavailable` and
`complete` is false; never call the result healthy. `status` still prioritizes
known unhealthy findings over incomplete evidence. The tool never repairs or
refreshes the store. Page with `offset`/`limit` (limit 1..500), and raise a work
bound only when the larger read is deliberate.

Graph import, reference, and call response envelopes are documented with
their exact raw syntax, support records, target identity, and failure reasons
in [graph-navigation.md](graph-navigation.md).

MCP tool errors are structured under `structuredContent.error` with `code`,
`message`, and `details`.
