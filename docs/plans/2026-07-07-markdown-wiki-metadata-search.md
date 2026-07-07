# Plan: make markdown wiki metadata searchable in loci

**Status:** ready to action
**For:** a fresh session in `/Users/brummerv/loci`
**Date:** 2026-07-07

This plan extends `docs/design/2026-06-13-markdown-indexing-design.md` and the
later markdown parser compatibility fix. Markdown is now indexed, but wiki-style
markdown is still weakly searchable because loci treats pages as generic heading
sections and ignores YAML frontmatter, tags, page type, category, source, and
description.

## TL;DR

Do not change the wiki format. Fix loci.

Add PyYAML as a real dependency, parse markdown YAML frontmatter with
`yaml.safe_load`, attach normalized metadata to page-root markdown symbols, and
teach search to score tags/category/type/source/description. Also fix
`loci verify` so synthetic markdown names like `(preamble)` do not fail the
code-oriented `name_not_in_bytes` check.

The target smoke case is:

```bash
loci index /Users/brummerv/phluxxed/ai_graph_ideas --incremental
loci search retrieval-governance --repo /Users/brummerv/phluxxed/ai_graph_ideas --lang markdown
loci verify /Users/brummerv/phluxxed/ai_graph_ideas
```

Expected result: search returns `ideas/governed-hybrid-retrieval-pipeline.md`,
and verify does not report false failures for `(preamble)` or headingless
fallback markdown symbols.

## Current Evidence

Observed against `/Users/brummerv/phluxxed/ai_graph_ideas`:

- `loci_index` indexes the repo: 877 symbols, 90 markdown files, 5 Python files.
- Markdown parsing works, but the symbol model is heading-driven: one `section`
  symbol per heading subtree.
- `scripts/query.py --type ideas --json` finds wiki pages through frontmatter
  fields such as `type`, `category`, and `tags`.
- `loci search retrieval-governance --lang markdown` returns no symbols even
  though `ideas/governed-hybrid-retrieval-pipeline.md` has that tag.
- `loci verify` reports false failures for synthetic markdown symbols because
  it assumes every symbol name must appear literally in the indexed byte range.

So the failure is not incompatible markdown. It is loci not understanding the
metadata layer that llm-wiki-style repos and Brain-style wikis rely on.

## Design Constraints

- Use PyYAML. Do not hand-roll YAML parsing.
- Keep markdown support generic. Do not call `scripts/query.py` or any
  repo-local wiki tool from loci.
- Preserve existing `section` symbols and `loci_get` byte-range behavior.
- Add output fields only additively and with defaults for old indexes.
- Make stale indexes reparse after the extractor/schema changes. Incremental
  indexing must not keep old markdown symbols that lack metadata.
- Keep templates searchable but downrank them so template headings do not beat
  real wiki pages.

## Interface Contract

### Dependency

Add PyYAML to `pyproject.toml` dependencies:

```toml
"PyYAML>=6",
```

Use `yaml.safe_load` only.

### Symbol metadata

Extend `Symbol` with an additive optional field:

```python
metadata: dict[str, Any] = field(default_factory=dict)
```

Include it in `to_dict()` and read it with `data.get("metadata", {})` in
`from_dict()` so existing indexes remain loadable.

Markdown page-root symbols may carry:

```json
{
  "frontmatter": {
    "title": "Governed Hybrid Retrieval Pipeline",
    "type": "ideas",
    "category": "Retrieval Governance",
    "status": "Draft",
    "source": "sources/chatgpt-graph-ai-brief-2026-07-04.md",
    "description": "Build bounded graph/vector context packs...",
    "tags": ["retrieval-governance", "graphrag", "context-packs", "loci"],
    "created": "2026-07-06",
    "last_reviewed": "2026-07-06",
    "timestamp": "2026-07-06T07:35:58Z"
  },
  "markdown": {
    "page_root": true,
    "synthetic_name": false
  }
}
```

Normalization rules:

- Keep only scalar fields needed for search and display; ignore unknown fields
  for v1.
- Convert dates/timestamps to strings before storing.
- Normalize `tags` and other list-like fields to `list[str]`.
- Do not expose parser node names such as `minus_metadata`.

### Page-root selection

Attach frontmatter metadata to page-root markdown symbols only, not every
subsection.

Page-root candidates:

1. Top-level headed sections in the file.
2. The no-heading fallback section when the file has no headings.

For normal wiki pages this is one H1-backed symbol. If a file has multiple
top-level headed sections, attach metadata to each top-level headed section so
frontmatter search still returns a real byte range instead of inventing a new
file-level symbol.

### Summary and keywords

For page-root markdown symbols:

- Keep `docstring` as the first direct paragraph, matching current behavior.
- Set `summary` from frontmatter `description` when present.
- Add normalized frontmatter words to `keywords`, especially:
  - `title`
  - `type`
  - `category`
  - `source`
  - `description`
  - `tags`

Do not change section byte ranges.

## Search Behavior

Update query tokenization and scoring in `IndexStore.search` / `_score_symbol`.

Current behavior uses `q.split()`, which treats `retrieval-governance` as one
opaque token. Replace that with a shared prose tokenizer that splits on
non-alphanumeric characters, lowercases, and drops one-character tokens. Reuse
the markdown `_prose_words` behavior or move it to a shared helper.

Scoring additions:

- Exact metadata tag match: high signal.
- Tag word overlap: medium signal.
- Category/type/source/status match: medium signal.
- Description/summary match: lower but useful signal.
- Keep heading/name/qualified-name matches as the strongest signal for direct
  symbol lookup.

Template handling:

- Downrank symbols under `_templates/`.
- Do not exclude them entirely; agents may still need template docs.
- Add a regression test proving a real page beats the matching template for a
  wiki metadata query.

Minimum expected search cases:

```bash
loci search retrieval-governance --repo <repo> --lang markdown
loci search "Retrieval Governance" --repo <repo> --lang markdown
loci search "context packs" --repo <repo> --lang markdown
```

All should find `ideas/governed-hybrid-retrieval-pipeline.md` in the target
wiki fixture.

## Verify Behavior

`IndexStore.verify_index()` currently checks `name in text` for every symbol.
That is useful for code byte-offset corruption, but false for some valid
markdown symbols:

- `(preamble)` is a synthetic name.
- No-heading markdown falls back to the file stem.
- Future markdown roots may use metadata-derived names.

Keep strict code verification. For markdown:

- Always verify source file exists.
- Always verify byte range can be read.
- Always verify `content_hash` against the live byte range when present.
- If `signature` is a real heading line, verify that signature appears in the
  byte range.
- Skip `name_not_in_bytes` for metadata-marked synthetic markdown symbols and
  for `(preamble)`.

This preserves drift detection without forcing synthetic labels to be literal
file content.

## Index Schema / Extractor Version

This is required.

Current incremental indexing keeps symbols for unchanged files based only on
file hash. After adding metadata, an unchanged markdown file would otherwise be
skipped and keep old metadata-less symbols forever.

Add an index schema or extractor version to `index.json`, for example:

```json
{
  "schema_version": 2,
  "extractor_version": 2,
  "symbols": []
}
```

Behavior:

- `IndexStore.write()` persists the current version.
- `index_repo(..., incremental=True)` treats missing or older versions as a
  full reindex.
- MCP read tools that auto-refresh stale indexes benefit automatically because
  their incremental refresh will become a real full reparse when needed.
- Tests cover a pre-version index file and assert markdown symbols are reparsed
  instead of silently reused.

## Tasks

### Task 1: Add metadata contract and PyYAML dependency

**Files likely touched:**

- `pyproject.toml`
- `src/loci/parser/symbols.py`
- `tests/parser/test_symbols.py`

**Acceptance criteria:**

- `Symbol.metadata` defaults to `{}`.
- `to_dict()` includes `metadata`.
- `from_dict()` loads old symbols with no `metadata` key.
- PyYAML is installed as a project dependency.

**Verification:**

```bash
.venv/bin/python -m pytest tests/parser/test_symbols.py -q
```

### Task 2: Parse YAML frontmatter into markdown page-root metadata

**Files likely touched:**

- `src/loci/parser/extractor.py`
- `tests/parser/test_markdown.py`

**Acceptance criteria:**

- Markdown frontmatter is parsed via `yaml.safe_load`.
- Page-root markdown symbols carry normalized `metadata.frontmatter`.
- Page-root `summary` uses frontmatter `description`.
- Page-root `keywords` include normalized tags/category/type/source words.
- Section byte ranges and existing heading extraction behavior remain unchanged.

**Verification:**

```bash
.venv/bin/python -m pytest tests/parser/test_markdown.py -q
```

### Task 3: Make search metadata-aware

**Files likely touched:**

- `src/loci/storage/index_store.py`
- `tests/storage/test_index_store.py`
- `tests/test_cli.py`

**Acceptance criteria:**

- Hyphenated queries are tokenized into useful words.
- Exact tag queries find metadata-bearing markdown page roots.
- Category and description queries find the relevant page.
- `_templates/` symbols are downranked below real pages for metadata queries.
- Existing code-symbol search behavior is not regressed.

**Verification:**

```bash
.venv/bin/python -m pytest tests/storage/test_index_store.py tests/test_cli.py -q
```

### Task 4: Fix markdown verification false positives

**Files likely touched:**

- `src/loci/storage/index_store.py`
- `tests/test_cli.py`
- `tests/test_service.py`

**Acceptance criteria:**

- `loci verify` passes for valid markdown with frontmatter plus preamble.
- `loci verify` still detects corrupted offsets for code.
- `loci verify` still detects content drift.
- Synthetic markdown names do not create `name_not_in_bytes` failures.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_cli.py tests/test_service.py -q
```

### Task 5: Add index/extractor versioning

**Files likely touched:**

- `src/loci/storage/index_store.py`
- `src/loci/service.py`
- `tests/test_service.py`
- `tests/test_cli.py`

**Acceptance criteria:**

- New indexes persist schema/extractor version.
- Missing/old version forces a full reindex even when file hashes match.
- Incremental indexing still skips files when both file hashes and extractor
  version are current.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_service.py tests/test_cli.py -q
```

### Task 6: Update public docs and smoke the real wiki

**Files likely touched:**

- `README.md`
- possibly `docs/design/2026-06-13-markdown-indexing-design.md`

**Acceptance criteria:**

- README symbol field list mentions `metadata`.
- Markdown docs explain that YAML frontmatter is searchable metadata.
- Real target wiki smoke passes.

**Verification:**

```bash
.venv/bin/python -m pytest -q
loci index /Users/brummerv/phluxxed/ai_graph_ideas --incremental
loci search retrieval-governance --repo /Users/brummerv/phluxxed/ai_graph_ideas --lang markdown
loci verify /Users/brummerv/phluxxed/ai_graph_ideas
```

## Done Criteria

- [ ] Full test suite passes.
- [ ] `retrieval-governance` finds `ideas/governed-hybrid-retrieval-pipeline.md`.
- [ ] Markdown metadata is available in search/outline/get output as additive
      `metadata`.
- [ ] Existing code search and verify behavior is preserved.
- [ ] Valid markdown preamble/no-heading files no longer fail verify.
- [ ] Existing indexes are reparsed because the schema/extractor version changed.
- [ ] No wiki-specific script dependency is introduced into loci.

## Risks and Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Additive output field surprises a strict consumer | Medium | Default to `{}`, document in README, and keep all existing fields unchanged. |
| Metadata search returns every subsection from a page | Medium | Attach metadata only to page-root symbols. |
| Incremental indexing keeps old metadata-less symbols | High | Add schema/extractor version and force reindex on old versions. |
| YAML parse edge cases | Medium | Use PyYAML, fail loudly with file path context, and test quoted strings/lists/dates. |
| Template headings pollute search results | Low | Downrank `_templates/` instead of excluding them. |
| Verify becomes too weak for markdown | Medium | Keep content-hash drift checks and heading-signature checks. Only relax synthetic name checks. |

## Out of Scope

- Calling llm-wiki or repo-local wiki query scripts from loci.
- Building wiki graph traversal or backlink inference.
- Semantic search or embeddings.
- Replacing heading-section symbols with a new markdown page abstraction.
- Changing `loci_get` byte-range output.
