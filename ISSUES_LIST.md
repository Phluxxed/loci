# Issues List

## Extraction

### ~~TSX: `export default function` not extracted~~ ✓ FIXED
Root cause: `.tsx` was mapped to the `typescript` tree-sitter parser, which can't parse JSX syntax.
Fix: added a `tsx` language spec using `ts_language="tsx"` and updated `EXTENSION_MAP[".tsx"]` to use it.

### ~~Maintained test files missing from the index~~ ✓ FIXED
Maintained tests and supported fixtures are indexed like other source files.
The shared repository-relative policy excludes only generated, cached,
vendored, build, temporary, ignored, sensitive, or unsupported material.

## Search

### ~~`vault` query returns 0 results~~ ✓ FIXED
Confirmed resolved after reindex. Was caused by the underscore keyword bug — `_vault` was stripping to nothing. Fixed by `_name_words` using `.strip("_")` before splitting.

### TypeScript interface cascade (38% blind spot)
When searching for a function, loci finds it correctly but doesn't surface the type dependencies
it references (interfaces, type aliases). Agent ends up fetching those separately as blind spots.
Hard problem — would require dependency graph awareness.
