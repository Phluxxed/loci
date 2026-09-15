# Issues List

## Extraction

### ~~TSX: `export default function` not extracted~~ ✓ FIXED
Root cause: `.tsx` was mapped to the `typescript` tree-sitter parser, which can't parse JSX syntax.
Fix: added a `tsx` language spec using `ts_language="tsx"` and updated `EXTENSION_MAP[".tsx"]` to use it.

### ~~Maintained test files missing from the index~~ ✓ FIXED
Maintained tests and supported fixtures are indexed like other source files.
The shared repository-relative policy excludes only generated, cached,
vendored, build, temporary, ignored, sensitive, or unsupported material.

### ~~TypeScript arrow-function `const` exports produce no symbol~~ ✓ FIXED
Found 2026-09-07 while covering the export-clause fix.

Fixed 2026-09-10 (W2.1.2): direct identifier bindings to arrow functions are
classified as functions before the uppercase-only constant filter, preserving
the declaration's exact source span. JavaScript, TypeScript and TSX share this
repair. Extractor version 22 forces stale indexes to rebuild. Focused regressions
assert the symbol, imported target and call edge with a same-name distractor.
The following describes the original failure; W2.1.1's evidence is retained.

`export const num = (v: unknown): number => Number(v)` in a `.ts` file yields no symbol from
`parse_file` — only the file node. The export record itself is extracted correctly (`local_name`
and `exported_name` both `num`, line 1), but nothing in the symbol index covers its definition span,
so a consumer importing `num` resolves to `unresolved` with reason `ambiguous_target`.

Consequence: this silently drops one of the most common TypeScript declaration forms from the
reference graph. No error is raised — `loci index` reports `healthy`, just with fewer resolved
references. That is why the repro script's "inline export const" case shows `ok`: the script only
checks for the absence of a `GraphContractError`, not for resolution.

Repro: the `inline-export-const` case in `.scratch/repro-export-clause-index-failure.sh`, or
materialize the two-file pair and assert `status == "resolved"`.

### ~~`export default <identifier>` produces no export record~~ ✓ FIXED
Found 2026-09-07 while covering the export-clause fix.

Fixed 2026-09-10 (W2.1.3): a direct default-export identifier now records its
authored export statement and binds to a unique module-level declaration.
Resolved support retains the export and declaration anchors separately;
missing or ambiguous declarations remain unresolved. Extractor version 23
refreshes old caches. The following describes the original failure.

`function num(...) {...}` followed by `export default num` extracts zero export records for that file,
so an importer resolves to `unresolved` with reason `target_not_indexed`. The inline form
(`export default function Factory() {}`) is extracted and already covered by
`tests/graph/test_references.py`. As with the arrow-const gap this fails silently rather than raising.

Repro: the `export default identifier` case in `.scratch/repro-export-clause-index-failure.sh`.

## Search

### ~~`vault` query returns 0 results~~ ✓ FIXED
Confirmed resolved after reindex. Was caused by the underscore keyword bug — `_vault` was stripping to nothing. Fixed by `_name_words` using `.strip("_")` before splitting.

### TypeScript interface cascade (38% blind spot)
When searching for a function, loci finds it correctly but doesn't surface the type dependencies
it references (interfaces, type aliases). Agent ends up fetching those separately as blind spots.
Hard problem — would require dependency graph awareness.

## Graph / reference validation

### ~~TypeScript export clauses make a repo unindexable~~ ✓ FIXED
Found 2026-09-07 on `/Users/brummerv/claude-otel`; fixed the same day.

Root cause: the export index in `_reference_validation.py::_build_validation_index` keyed each export
only by the line of the *export statement*, while a resolver anchors `definition` support on the line of
the declaration the export resolves to. For an inline export those lines coincide, so only the
two-statement shape (`export { num }`, `export { numHelper as num }`) could ever mismatch.

Fix: register both anchors for the same export — the export statement's line and the resolved endpoint's
own line — since the per-language resolvers legitimately stamp either one (JavaScript/TypeScript and Rust
use the declaration line, Python/Go/Swift the export statement line).

Covered by `tests/graph/test_materialize.py::test_typescript_export_shapes_resolve_references_with_current_support`
(inline export control plus both export-clause shapes, asserting the support anchors, not just the absence
of an error). `bash .scratch/repro-export-clause-index-failure.sh` exits 0 and
`loci index /Users/brummerv/claude-otel` reports `graph_status: healthy`.

## Retrieval payload

### `loci_grep` is unbounded and inlines context for every match

Found 2026-09-15 while porting weave. Not yet fixed in loci; fixed in weave, so
the diff below is a known-good shape rather than a proposal.

`loci_grep(repo, pattern)` takes no other arguments.
`IndexStore.grep_files` (`src/loci/storage/index_store.py:763`) walks every
cached file line by line and appends every match with two lines of context
either side. No limit, no path filter, no context control, no total count. A
broad pattern therefore returns the whole result, however big it is.

Measured on a 670-file repository (`lotteries-intelligent-optimization-nexus-engine-master`):

| pattern | matches | payload |
| --- | --- | --- |
| `elasticit` | 1,479 | 665 KB |
| `[Ss]aturday` | 1,152 | 511 KB |
| `_SAT_ELASTICITY_PATH\s*=` | 3 | 3.3 KB |

Roughly 60% of each match's bytes are the four context lines the caller did not
ask for. `loci_search` already has `limit=20`, `kind`, `lang` and `file_paths`,
so grep is the one retrieval tool with no bounds at all.

Why it matters beyond the byte count: an agent that greps broadly gets a result
too large to read, pays for it, and discards it. In a three-question acceptance
run the question that grepped broadly cost 54,001 tokens and 11 tool uses
against 20,288 and 3 for the question that outlined first. After the weave fix
the same question cost 32,627 tokens and 7 tool uses, with the grep payload for
its four patterns falling from 1,179 KB to 34 KB.

Fix (as landed in weave):

- `grep_files(repo_path, pattern, limit=None, file_paths=None, context=0)`
  returns `{matches, total_matches, total_files, truncated}` instead of a bare
  list. Keep counting past `limit` so the caller learns the real size.
- `context` defaults to 0, so a match is one line — `file`, `line`, `match`.
  `context_before`/`context_after` are omitted entirely unless asked for.
- `grep_repo_result` threads `limit` (default 50), `file_paths` and `context`,
  and rejects `limit < 1` and `context < 0` as `INVALID_INPUT`.
- The MCP tool's docstring tells the caller what to do when `truncated` is
  true — narrow the pattern or pass `file_paths`, rather than raise `limit` —
  and points at `loci_file` with the returned line number for widening one
  match, or `loci_get` when the enclosing symbol is what is wanted.

That last point closes a loop that currently has no producer: `loci_file`
accepts `start_line`/`end_line`, and `outline`/`get`/`search` all emit line
numbers, but nothing produces a line range for a text hit. Across the three
acceptance agents — 15 tool calls — `loci_file` was called zero times.

### Outline spends ~200 bytes of JSON envelope per symbol

Same origin, same session, also fixed in weave only. `loci_outline` returns one
JSON object per symbol carrying the full file path inside `id`, plus `name` and
`kind` that the id already contains, `end_line`, and a `summary` that is empty
on every symbol in the repositories measured.

Re-emitting the same symbols as declaration text — a per-file header with the
file's byte size and symbol count, then `start line`, short id, declaration —
measured 63–65% smaller across three repositories (Swift, TypeScript, Python).
Replaying 389 real whole-file reads from Claude Code telemetry, the saving over
reading the file went from 39% to 71% at one symbol, and from 5% to 37% at four.
Before the change the outline exceeded the size of its own source on 101 of 287
touched files; after it, on none, in any of the three repositories.

The id shortening is a prerequisite, not an optimisation: `get` has to accept
`file` plus a short id before the outline can stop repeating the path. Note
`index_store.py` recovers a symbol's file for the per-file retrieval stats with
`entry["symbol_id"].split("::", 1)[0]`, which silently regroups by symbol if
the id loses its prefix — weave keeps full ids internally and shortens only the
outline's output.
