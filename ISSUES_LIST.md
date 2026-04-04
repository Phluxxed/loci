# Issues List

## Extraction

### ~~TSX: `export default function` not extracted~~ ✓ FIXED
Root cause: `.tsx` was mapped to the `typescript` tree-sitter parser, which can't parse JSX syntax.
Fix: added a `tsx` language spec using `ts_language="tsx"` and updated `EXTENSION_MAP[".tsx"]` to use it.

### ~~Test file constants inflating the index~~ ✓ FIXED
Test files are now excluded entirely at index time.
Skipped via `SKIP_DIRS` (`__tests__`, `tests`) and `_should_skip_file` patterns (`test_*.py`, `*_test.py`, `*_test.go`, `*.test.*`, `*.spec.*`).

## Search

### ~~`vault` query returns 0 results~~ ✓ FIXED
Confirmed resolved after reindex. Was caused by the underscore keyword bug — `_vault` was stripping to nothing. Fixed by `_name_words` using `.strip("_")` before splitting.

### TypeScript interface cascade (38% blind spot)
When searching for a function, loci finds it correctly but doesn't surface the type dependencies
it references (interfaces, type aliases). Agent ends up fetching those separately as blind spots.
Hard problem — would require dependency graph awareness.
