# Shared multilingual exploration interface

W4.6 (`task_5463db0ee464fec8e1bc4db41ab17986`) verifies the common source and
evidence interface after the four language slices and repairs the frozen TSX
anchor defect. Work remains on `feat/evidence-backed-exploration`.

## Delivered behavior

JSX-bearing `.tsx` files now use the TSX grammar during declaration extraction,
through both the primary parser and the high-level process fallback.
Their public language identity remains `typescript`, matching the existing
type, import, reference and call adapters, which already selected that grammar.
Frozen `Badge` is an exact function at bytes 45–112 and reaches the authored
`Props` interface. JSX itself creates no call edge. Extractor version 30 forces
old indexes to rebuild; graph and public response schemas are unchanged.

The [implemented capability matrix](../../skills/loci/references/language-resolution.md#exploration-capabilities)
records navigation, both dependency intents, known impact, origin evidence and
partial/unsupported semantics for Python, JavaScript, TypeScript/TSX, Go and Rust,
plus Markdown navigation. README, MCP tool descriptions and repository Loci
guidance now reflect those boundaries.

JavaScript/TypeScript resolver controls participate in validation and refresh;
their paths/hashes remain diagnostic metadata, and their full contents require
a separate read. Go/Rust packets hydrate complete contained control source.
The compatibility `loci_get` expansion follows outgoing type records with
supporting lines; exploration supplies full selected import/re-export statements
and the Go/Rust control, Rust configuration and reverse impl-selection behavior.
These distinctions prevent a shared schema from implying semantic parity.

## Acceptance against the four criteria

| Criterion | Direct evidence |
| --- | --- |
| Normal MCP delivery across the five families | Existing Python, JavaScript, Go and Rust context MCP suites exercise dependency definitions and origin proof through the real stdio server. Three new shared tests use the same normal SDK host, with all five families and Markdown present in one repository. TSX search → selected exact get with type context → exploration verifies `Badge` and `Props`; Markdown search uses its returned qualified section ID and preserves the exact nested UTF-8 section and peer boundary. |
| Shared source/result bounds and atomicity | New shared packet assertions validate the strict schema, complete serialized `CallToolResult` bytes, union of unique source intervals, exact file hashes/text, source and relationship deduplication and closed item/proof paths. Real stdio cycle and zero-budget checks complement existing clipping, reduced budgets, atomic bundle omission, hop/node/neighbor/item bounds and structured-error checks. |
| Mixed languages and refresh | Same-name Python/TypeScript `Request` declarations resolve only from their own authored signatures. Removing Python's declaration stays unresolved despite the TypeScript distractor. A source edit appears on the next MCP read; a Go module-control edit invalidates the old imported target without substituting another language's `Request`. Existing exact navigation, TypeScript contract controls, parser import/reference/call and storage checks pass. |
| Published truthful capability guidance | The linked matrix and repository tool guidance distinguish supported authored relationships, explicit uncertainty, JS/TS control-source limits, Go embedding, Rust configuration/impl sites, and legacy get versus exploration. |

The host checks launch the checkout's Python MCP server over stdio with an
isolated cache and namespace and invoke public tool names. They test normal
protocol delivery, rather than calling handlers or merely listing tools. They
do not replace or promote the ambient shared installation.

## Verification

- **273 passed** in the initial focused parser/storage set: `tests/parser/test_extractor.py`,
  `test_references.py`, `test_calls.py`, `test_type_observations.py`, and
  `tests/storage/test_index_store.py`. The new parser regression verifies exact
  TSX declaration text and TypeScript identity. A direct pinned-fixture check
  confirms the exact `Badge` span, imported `Props` and absence of JSX calls.
- **86 passed** in the existing shared acceptance command below. This includes
  the existing frozen TypeScript source controls and actual language MCP calls.
- **3 passed** in `tests/test_multilingual_context_mcp.py` after strengthening
  the same-name relationship negative; these are the new shared stdio checks.
- After the final fallback repair, **52 passed** across the complete extractor
  file and new shared MCP file, including a forced-primary-failure TSX regression.
  These verification sets overlap.
- Corpus hash/source validation passes: **19 cases / 16 snapshots**. The
  multilingual inputs and old seventeen-case TypeScript corpus are unchanged.
- Repository skill validation and `git diff --check` pass.

```sh
.venv/bin/python -m pytest -q \
  tests/test_exploration.py tests/test_exploration_output.py \
  tests/test_exploration_wire.py tests/test_exploration_mcp.py \
  tests/test_python_context_mcp.py tests/test_javascript_context_mcp.py \
  tests/test_go_context_mcp.py tests/test_rust_context_mcp.py \
  tests/test_type_context.py tests/test_type_context_mcp.py \
  tests/test_type_relations_mcp.py tests/test_mcp_output_schemas.py
.venv/bin/python -m pytest -q \
  tests/parser/test_extractor.py tests/test_multilingual_context_mcp.py
```

Bounded review repaired the TSX process fallback, corrected the JS/TS
control-source documentation and replaced a weak exact-seed isolation assertion
with a real cross-language type-resolution negative. The nested Markdown ID and field-selection test setup were aligned
with the existing navigation and relevance contracts; neither required a
production behavior change.

## Next boundary

The four recorded declaration gaps from W4.1 are now repaired. This milestone
establishes shared source delivery within the retained budgets; it makes no new
provider outcome, general semantic parity or runtime impact completeness claim.
Historical results, including the rejected TypeScript comparison, remain intact.

Next is W4.7 — measure multilingual usefulness and record delivery decisions,
`task_ecbfc0ce724b713f2599830d21438a46`. Freeze the final implementation, effective
schema, provider/model/host, scorer, accounting and schedule there before any
provider outcomes. Runtime integration or promotion remains a separate decision.
