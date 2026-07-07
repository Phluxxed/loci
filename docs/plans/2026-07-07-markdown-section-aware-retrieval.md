# Plan: make markdown retrieval section-aware in loci

**Status:** implemented
**For:** a fresh session in `/Users/brummerv/loci`
**Date:** 2026-07-07

This plan follows `docs/plans/2026-07-07-markdown-wiki-metadata-search.md`.
The metadata/search fix makes wiki pages discoverable through YAML frontmatter,
but markdown retrieval savings can still be poor because page-root heading
symbols span nearly the whole file. The next fix is to make search and outline
page-aware enough that agents naturally choose smaller useful sections.

## TL;DR

Do not change wiki format and do not make `get` clever.

Keep exact markdown byte-range semantics:

- `# Page Title` returns the whole page subtree.
- `## Section` returns that section subtree.
- `### Subsection` returns that subsection subtree.

Add markdown hierarchy and retrieval-cost metadata to indexed symbols, expose
that cost in search/outline output, and update markdown search ranking so page
metadata can help identify relevant child sections without pretending the child
section directly owns the page's frontmatter.

The target smoke case is:

```bash
loci index /Users/brummerv/phluxxed/ai_graph_ideas --incremental
loci search retrieval-governance --repo /Users/brummerv/phluxxed/ai_graph_ideas --lang markdown
loci outline /Users/brummerv/phluxxed/ai_graph_ideas --file wiki-agent.md
loci get "wiki-agent.md::AI Graph Ideas Wiki Agent Manual > Operations > Query#section" --repo /Users/brummerv/phluxxed/ai_graph_ideas
loci stats --repo /Users/brummerv/phluxxed/ai_graph_ideas
```

Expected result: root page symbols remain valid, but search/outline clearly show
retrieval cost, and relevant child sections become easy/preferred retrieval
targets when the query does not explicitly ask for the whole page.

## Current Evidence

Observed against `/Users/brummerv/phluxxed/ai_graph_ideas` after the metadata
fix:

```text
wiki-agent.md root                         14,315 / 14,315 bytes = 0% saved
wiki-agent.md > Query                         802 / 14,315 bytes = 94% saved
wiki-agent.md > Wiki Page Frontmatter       1,474 / 14,315 bytes = 89% saved

governed pipeline root                      5,123 / 5,649 bytes = 9% saved
governed pipeline > Proposed Graph Move     1,843 / 5,649 bytes = 67% saved
governed pipeline > Open Questions            277 / 5,649 bytes = 95% saved

idea-distiller root                        15,853 / 16,335 bytes = 2% saved
idea-distiller > Proposed Graph Move        5,197 / 16,335 bytes = 68% saved
idea-distiller > Extraction Gate              741 / 16,335 bytes = 95% saved
```

The markdown section model is correct. The problem is result selection:

- page-root symbols are valid but expensive;
- child sections are efficient but do not carry page frontmatter;
- metadata queries naturally favor page roots because frontmatter is page-level;
- search/outline output does not make retrieval cost obvious enough.

This is analogous to class/method retrieval in code: the class span is valid,
but a method span is usually the better retrieval unit.

## Design Constraints

- Preserve `get(id)` as exact byte-range retrieval. Never silently substitute a
  child section, summary, or generated context pack.
- Keep YAML frontmatter page-level. Do not blindly copy frontmatter to every
  child section as owned metadata.
- Preserve existing symbol IDs and byte ranges where possible.
- Add fields additively and default old indexes safely.
- Force stale indexes to reparse by bumping extractor/schema version.
- Keep markdown support generic. Do not depend on llm-wiki repo-local scripts.
- Make retrieval cost visible to agents and humans, not hidden in stats only.

## Interface Contract

### Markdown Hierarchy Metadata

Extend markdown symbols with stable hierarchy data under `metadata.markdown`.
Page-root symbols already carry some of this structure from the metadata fix;
this plan expands it.

Expected shape:

```json
{
  "metadata": {
    "frontmatter": {
      "title": "Governed Hybrid Retrieval Pipeline",
      "tags": ["retrieval-governance"]
    },
    "markdown": {
      "page_root": false,
      "synthetic_name": false,
      "heading_level": 2,
      "parent_id": "ideas/page.md::Page#section",
      "root_id": "ideas/page.md::Page#section",
      "file_bytes": 5649,
      "saved_pct": 67,
      "span_kind": "section"
    }
  }
}
```

Field rules:

- `heading_level`: integer heading level for ATX headings; `0` for synthetic
  preamble/no-heading fallback when no real heading exists.
- `parent_id`: parent markdown section id, or `""` for root/preamble without a
  parent.
- `root_id`: page-root section id for this symbol, or the symbol's own id when
  it is the root/fallback.
- `file_bytes`: full source file byte size.
- `saved_pct`: integer `0..100`, calculated as
  `int((file_bytes - byte_length) / file_bytes * 100)` when `file_bytes > 0`.
- `span_kind`: `"page_root"`, `"section"`, `"preamble"`, or `"flat_page"`.

Do not add markdown-only top-level `Symbol` fields unless the codebase already
has a compelling generic need for them. Prefer `metadata.markdown` for this
slice.

### Search / Outline Output

Search results and outline symbols should expose retrieval-cost fields at the
top level for agent ergonomics, copied from metadata:

```json
{
  "id": "...",
  "name": "Query",
  "kind": "section",
  "language": "markdown",
  "byte_length": 802,
  "line": 91,
  "end_line": 105,
  "file_bytes": 14315,
  "saved_pct": 94,
  "span_kind": "section",
  "match_scope": ["section_heading", "inherited_page_frontmatter.tags"]
}
```

Rules:

- Existing fields stay unchanged.
- New fields are optional/additive.
- `match_scope` is only required on search results, not outline.
- Code symbols may omit `file_bytes`, `saved_pct`, `span_kind`, and
  `match_scope`.

### Match Scope

Search should distinguish why a markdown result matched:

- `section_heading`: direct match on the section name/qualified name.
- `section_summary`: direct match on section summary/docstring.
- `section_keywords`: direct match on section keywords.
- `page_frontmatter.title`: direct match on the page-root frontmatter title.
- `page_frontmatter.tags`: direct match on page-root tags.
- `page_frontmatter.category`: direct match on page-root category.
- `page_frontmatter.type`: direct match on page-root type.
- `page_frontmatter.description`: direct match on page-root description.
- `inherited_page_frontmatter.*`: match inherited from the page root, not owned
  by the child section.

This is intentionally diagnostic. Agents should be able to see whether a child
section matched its own heading/content or was surfaced because the containing
page matched metadata.

## Ranking Behavior

### Direct Section Matches

If a query directly matches a child heading, qualified heading path, docstring,
summary, or section keywords, rank that child normally. Do not penalize it for
not being a page root.

Example:

```bash
loci search "Query" --repo <wiki> --lang markdown
```

Expected: `wiki-agent.md > Operations > Query` should outrank the
`wiki-agent.md` root.

### Page Metadata Matches

If a query matches page frontmatter only:

1. Include the page root as a result.
2. Also consider child sections from that page as inherited metadata candidates.
3. Prefer child sections that have useful section-local signals:
   - heading words overlap the query;
   - docstring/summary/body keywords overlap the query;
   - conventional wiki headings likely to contain actionable detail, such as
     `Problem Signal`, `Proposed Graph Move`, `Evidence To Gather`,
     `Next Experiment`, `Risks And Failure Modes`, `Query`, `Usage`,
     `Operations`, or `Frontmatter`.
4. Apply a retrieval-cost adjustment so a very large page-root result does not
   beat a relevant small child by default.

Use conservative scoring. The goal is to surface efficient candidates, not to
hide page roots completely.

### Page Root Handling

Page roots are still valid and should win when the query is clearly page-level:

- exact page title query;
- query asks for overview/manual/page;
- there is no child section with any local signal;
- the root is small enough that retrieval cost is not meaningful.

Possible first-pass rule:

- For markdown `span_kind="page_root"` with `saved_pct < 25`, apply a modest
  ranking penalty unless the exact page title matched.
- For child sections with inherited page metadata and `saved_pct >= 50`, apply
  a modest boost when they also have section-local signal.

Do not hard-exclude roots.

### Templates

Keep the existing `_templates/` downrank. It should apply after metadata and
section-cost scoring.

## Implementation Tasks

### Task 1: Add markdown hierarchy metadata

**Files likely touched:**

- `src/loci/parser/extractor.py`
- `tests/parser/test_markdown.py`

**Acceptance criteria:**

- Markdown symbols include `metadata.markdown.heading_level`.
- Child sections include `parent_id` and `root_id`.
- Root/no-heading/preamble sections have correct `span_kind`.
- `file_bytes` and `saved_pct` are calculated for markdown symbols.
- Existing byte ranges and symbol IDs remain stable.

**Verification:**

```bash
.venv/bin/python -m pytest tests/parser/test_markdown.py -q
```

### Task 2: Expose retrieval-cost fields in outline/search

**Files likely touched:**

- `src/loci/service.py`
- `src/loci/storage/index_store.py`
- `src/loci/cli.py`
- `src/loci/mcp_server.py` if it shapes outputs separately
- `tests/test_cli.py`
- `tests/test_service.py`
- `tests/test_mcp_server.py`

**Acceptance criteria:**

- Markdown outline output includes `file_bytes`, `saved_pct`, and `span_kind`.
- Markdown search output includes `file_bytes`, `saved_pct`, `span_kind`, and
  `match_scope`.
- Code output remains backward compatible.
- Pretty stats/search displays remain readable.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_cli.py tests/test_service.py tests/test_mcp_server.py -q
```

### Task 3: Make search page-aware without copying metadata ownership

**Files likely touched:**

- `src/loci/storage/index_store.py`
- `tests/storage/test_index_store.py`
- `tests/test_cli.py`

**Acceptance criteria:**

- Page-root frontmatter still matches metadata queries.
- Child sections can be surfaced with `inherited_page_frontmatter.*` match scope.
- Child sections with local section signal and high `saved_pct` can outrank a
  low-savings root for tag/category queries.
- Exact page-title queries still return the page root at or near the top.
- `_templates/` results remain downranked.

**Verification:**

```bash
.venv/bin/python -m pytest tests/storage/test_index_store.py tests/test_cli.py -q
```

### Task 4: Bump index/extractor version

**Files likely touched:**

- `src/loci/storage/index_store.py`
- `src/loci/service.py`
- `tests/test_service.py`

**Acceptance criteria:**

- `EXTRACTOR_VERSION` or schema version increments from the metadata-search
  implementation.
- Existing indexes without hierarchy/cost metadata force a full reparse during
  incremental indexing.
- Current-version incremental indexing still skips unchanged files.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_service.py -q
```

### Task 5: Update docs and smoke the real wiki

**Files likely touched:**

- `README.md`
- `docs/design/2026-06-13-markdown-indexing-design.md`
- possibly `docs/plans/2026-07-07-markdown-wiki-metadata-search.md` only if
  adding a short superseded/follow-up note

**Acceptance criteria:**

- README explains markdown section cost fields.
- Design docs clarify that page roots are valid but expensive retrieval units.
- Real wiki smoke demonstrates both root and child retrieval savings.

**Verification:**

```bash
.venv/bin/python -m pytest -q
LOCI_BASE_DIR=/tmp/loci-md-section-smoke .venv/bin/python -m loci.cli index /Users/brummerv/phluxxed/ai_graph_ideas --incremental
LOCI_BASE_DIR=/tmp/loci-md-section-smoke .venv/bin/python -m loci.cli search retrieval-governance --repo /Users/brummerv/phluxxed/ai_graph_ideas --lang markdown --limit 10
LOCI_BASE_DIR=/tmp/loci-md-section-smoke .venv/bin/python -m loci.cli outline /Users/brummerv/phluxxed/ai_graph_ideas --file wiki-agent.md
LOCI_BASE_DIR=/tmp/loci-md-section-smoke .venv/bin/python -m loci.cli verify /Users/brummerv/phluxxed/ai_graph_ideas
```

## Suggested Regression Fixture

Create a markdown fixture with:

```markdown
---
title: Governed Hybrid Retrieval Pipeline
category: Retrieval Governance
tags:
  - retrieval-governance
description: Build bounded context packs.
---

# Governed Hybrid Retrieval Pipeline

## Problem Signal

The current retrieval process loads too much context.

## Proposed Graph Move

Use page-level governance metadata to route to bounded section-level context.

## Open Questions

- Which sections should be inherited candidates?
```

Expected search behavior:

- `retrieval-governance` returns the root and relevant child candidates.
- `Proposed Graph Move` outranks the root for that phrase.
- Child candidate result has `match_scope` containing both
  `inherited_page_frontmatter.tags` and a section-local scope.
- Child candidate has higher `saved_pct` than the root.

## Done Criteria

- [x] Full test suite passes.
- [x] Search and outline expose markdown retrieval-cost fields.
- [x] `get(id)` remains exact byte-range retrieval.
- [x] Page frontmatter remains page-level owned metadata.
- [x] Metadata queries can surface efficient child-section candidates.
- [x] Exact page-title searches still keep root-page results discoverable.
- [x] Old indexes reparse because the extractor/schema version changed.
- [x] `ai_graph_ideas` smoke confirms root symbols remain valid and efficient
      child sections are obvious/preferred.

Implementation verification:

```bash
.venv/bin/python -m pytest -q
# 228 passed

LOCI_BASE_DIR=/tmp/loci-md-section-smoke .venv/bin/python -m loci.cli index /Users/brummerv/phluxxed/ai_graph_ideas --incremental
# 918 symbols; 94 markdown files; 5 python files

LOCI_BASE_DIR=/tmp/loci-md-section-smoke .venv/bin/python -m loci.cli search retrieval-governance --repo /Users/brummerv/phluxxed/ai_graph_ideas --lang markdown --limit 5
# Top results are efficient child sections; the page root remains visible with saved_pct=9.

LOCI_BASE_DIR=/tmp/loci-md-section-smoke .venv/bin/python -m loci.cli verify /Users/brummerv/phluxxed/ai_graph_ideas
# 918 checked; 918 passed
```

## Risks and Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Search becomes noisy by surfacing every child from a matching page | High | Require at least one section-local signal before boosting inherited candidates. Limit inherited candidates per page if needed. |
| Agents miss whole-page context when it is actually needed | Medium | Keep roots in results and let exact page-title/overview/manual queries favor roots. |
| Output shape surprises strict consumers | Medium | Add fields only additively; code symbols may omit markdown-only fields. |
| Ranking becomes hard to reason about | Medium | Emit `match_scope` and keep scoring rules small/tested. |
| Metadata ownership becomes ambiguous | High | Keep frontmatter only on page roots; use `inherited_page_frontmatter.*` scopes for child search matches. |
| Existing indexes keep old hierarchy metadata | High | Bump extractor/schema version and test old-index reparse. |

## Out of Scope

- Changing wiki file format.
- Copying frontmatter into every child section as owned metadata.
- Semantic search or embeddings.
- Generated summaries/context packs.
- Changing `loci_get` to return anything other than the exact requested symbol.
- Building full markdown link/backlink graph traversal.
