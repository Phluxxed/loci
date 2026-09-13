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
