# R0.5 demand semantics implementation notes

## Interface and boundary

`DemandSource(GraphFreeSource)` preserves the R0.4 `index_repo`, `inventory`,
`retrieve`, and ordinary `read` behavior. `semantic_context(repo, query,
anchor_file=None)` is the only parsing/resolution entry point. It returns a
normal-shaped `demand-semantic-v1` packet. `semantic_observer()` returns a
separate `{index, work}` receipt. The index is an ephemeral, native-shaped
scorer projection for the resolved request slice, including unresolved records;
it is never persisted as a semantic graph. Only the latest identical question
is cached in memory, keyed to a refreshed full inventory digest. `read` accepts
`s:` references for exact semantic symbol extents and rechecks membership,
source hash, containment, and UTF-8 boundaries; ordinary R0.4 refs are delegated.

The graph-free inventory remains source-only. Semantic work scans admitted
current JS/TS/Rust bytes, builds file-only nodes for **all** admitted supported
files, and snapshots the chosen bytes and applicable controls into a contained
temporary directory. The selected files are parsed using existing `parse_file`,
`extract_import_batch`, and `extract_type_observations`; existing import,
reference, call, and type resolvers operate on the temporary request slice.
The Rust pass follows touched crate roots and observed external `mod` paths.
Resolved local imports receive at most two closure rounds. Normal graph
materialization, service indexing, and repository-wide semantic storage never
run. Rust source bytes are copied into the temporary snapshot so native Cargo
target discovery can check target existence; those copies are counted separately
and are not parsed by that copy step.

Anchors require an exact identifier token or admitted file candidate. The
output follows native edges forward and reverse, independently, for at most two
hops. It emits targeted source items even when the full strict relation proof
cannot fit. A relationship is emitted only when the complete caller/target,
site, import/reexport/module, configuration, and control support fits the
8 KiB unique evidence and 16 KiB complete MCP envelope budgets. Imported calls
must join a unique resolved reference record and carry its support. Native
Rust `declared_possible` configuration is preserved. Incomplete inventory,
stale source, capped Rust closure, or unparsed reexport routes suppress affected
import-resolved claims; the packet and observer retain explicit omissions.

## Work receipt

The `work` receipt exposes timed phases (`cachevalidate`, `discovery`,
`snapshot`, `extraction`, `control_parse`, closure, resolution, proof packing,
and final freshness), CPU deltas and peak RSS. It reports initial and final
inventory scans, discovered paths/bytes, parsed paths and parser-input bytes,
control and Rust snapshot paths/bytes, raw/resolved record counts, eligible
two-hop edges, emitted items/relationships, closure and proof omissions, and
cache hit status. `cache_serialized_proxy_bytes` counts serialized retained
packet and native index bytes; it is a proxy, not heap size. The initial index
and source-only retrieval have no semantic preparation.

## Focused verification and limits

`PYTHONPATH=src /Users/brummerv/phluxxed/loci/.venv/bin/python -m pytest -q
tests/test_demand_semantics.py` passes 7 tests. They cover source-only isolation,
exact TypeScript call/reference proof, repeat cache and source/membership
invalidation, source mutation during parsing, unknown-language and ambiguous
anchors, parse-cap omission, unique-byte evidence accounting, and an optional
Rust workspace queried through its actual entry function. Separate smoke runs
validated the packet shape and budgets against `validate_demand_packet` for a
small TypeScript fixture and the retained Anvil source archive. The Anvil
identifier query delivered targeted `retrieve.ts` type declarations while
omitting oversized relations honestly. Rust source-archive smoke retained
`declared_possible` on an optional import.

This first candidate supports JS/TS and Rust semantic parsing. Python, Go,
and other admitted text remain source-only. A broad source-text prefilter can
miss plausible candidates, so `scope.exhaustive` is always false. Parsing is
bounded to 48 files, 10 reverse candidates, two local import rounds, and 32
Rust module iterations. No absence or impact completeness follows from a
zero-edge response. The full deterministic comparison and independent strict
scoring are owned by the parent harness.
