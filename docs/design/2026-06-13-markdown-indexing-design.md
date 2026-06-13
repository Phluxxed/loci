# loci: markdown indexing — Design

**Goal:** Make markdown files first-class citizens in the loci index — `outline`, `get`, `search`, and `grep` work on `.md`/`.markdown` exactly as they do on code — so the repo's growing pile of design docs, specs, and notes becomes navigable instead of invisible.

**Architecture:** Add a *parallel* markdown extraction path (`parse_markdown()`) alongside the existing tree-sitter code path in `parser/extractor.py`. It returns the existing `Symbol` dataclass unchanged, so storage, the sources mirror, and every read command work with **zero downstream changes**. Markdown's unit is the **section** (a heading plus everything beneath it until the next same-or-higher heading), nested by heading level. Inclusion is a two-line touch: register `.md`/`.markdown` in `EXTENSION_MAP` and dispatch on suffix in `parse_file`.

**Tech Stack:** Python (existing). Parsing = `tree-sitter-language-pack`'s bundled `markdown` grammar — **no new dependency** (verified available; see Current state). Only the block grammar (`markdown`) is needed; the `markdown_inline` grammar is *not* required, because heading text is recovered by byte-slicing the `inline` child.

---

## Why this doc exists

loci is auto-indexed at session start and is the mandated navigation tool for this repo, but it is blind to markdown. The repo now generates "a metric fucktonne" of markdown — design docs (this directory), `ISSUES_LIST.md`, `README.md`, skill docs — with no symbol-level way to track or navigate them. An agent asked "where's the section on cross-file resolution in the graph design?" has to fall back to `Read`/`Grep`, which is exactly what loci exists to replace.

## Current state (audit, 2026-06-13)

Confirmed by source audit:

- **loci's model is code-shaped.** `LanguageSpec` (`parser/languages.py:6`) assumes symbols are named via a tree-sitter **field** (`child_by_field_name`, `extractor.py:523`), plus `param_fields`, `return_type_fields`, `docstring_strategy`, `decorator_*` — all meaningless for prose. Nesting is **single-level** (`container_node_types` does class→method, one hop; `extractor.py:422`).
- **`kind` is an opaque string end-to-end.** `cmd_outline` (`cli.py:577`) emits every symbol grouped by file regardless of kind; `cmd_get`/`cmd_search` pass `kind` straight through; the symbol id is `{rel_path}::{qualified_name}#{kind}` (`cli.py:104`). **A new `kind` value flows through with no CLI changes.** *(Verified.)*
- **File discovery** is `repo_path.rglob("*")` in `cmd_index` (`cli.py:80`), gated by `_should_skip_file` (`cli.py:47`), which **rejects any suffix not in `EXTENSION_MAP`** (`cli.py:52`). Respects `.gitignore` (`cli.py:89`) and `SKIP_DIRS` (`cli.py:18`, includes `tests`/`__tests__`).
- **Dispatch point:** `parse_file` (`extractor.py:13`) maps suffix→language via `EXTENSION_MAP` and returns `[]` for unknown suffixes.
- **The markdown grammar is available** in the installed `tree-sitter-language-pack`. *(Verified: `get_parser("markdown")` parses to `document → section` nodes.)*

### Why markdown does not fit `LanguageSpec`

The generic `_walk` machinery (`extractor.py:394`) has nothing to grab onto for markdown: headings have **no name field** (the text is the `inline` content), the param/return/docstring/decorator attributes are inapplicable, and the one-level container model cannot express an arbitrarily deep H1>H2>H3>… tree. Shoehorning markdown into a `LanguageSpec` means special-casing the generic extractor until it *is* a markdown parser wearing a `LanguageSpec` hat. A dedicated path is cleaner and leaves the code path untouched.

## How the markdown grammar helps (verified AST)

The `markdown` grammar already produces a **nested `section` tree** that matches our desired output almost exactly. For:

```markdown
---
title: Doc
---

preamble text

# Top H1

intro

## Sub A

body a

### Deep

deep body
```

the tree is:

```
document
  minus_metadata          # YAML frontmatter (---...---)
  section                 # preamble: no atx_heading child
    paragraph
  section                 # spans "# Top H1" → end of its whole subtree
    atx_heading
      atx_h1_marker        # marker node → heading level (h1..h6)
      inline               # heading TEXT
    paragraph
    section                # "## Sub A", nested
      atx_heading (h2) ...
      section              # "### Deep", nested deeper
```

Key properties we exploit:
1. A `section` node's **byte span already runs from its heading to the end of all its nested content** — exactly the body `get` should return.
2. The first child of a `section` is its `atx_heading`; the `atx_hN_marker` child gives the **level**, the `inline` child gives the **text**.
3. Subsections are nested `section` children — recursion gives the full path for free.
4. A leading `section` with **no `atx_heading`** = document preamble. `minus_metadata` = frontmatter.

## Design

### `parse_markdown(path) -> list[Symbol]`

A new function in `parser/extractor.py`, dispatched from `parse_file` before the tree-sitter code path:

```python
def parse_file(path: Path) -> list[Symbol]:
    suffix = path.suffix.lower()
    if suffix in MARKDOWN_SUFFIXES:        # {".md", ".markdown"}
        return parse_markdown(path)
    language = EXTENSION_MAP.get(suffix)
    ...
```

`parse_markdown` parses with `get_parser("markdown")` and recursively walks `section` nodes, emitting one `Symbol` per heading. It reuses the existing `_disambiguate` helper (`extractor.py:645`) for duplicate-heading collisions.

### Symbol field mapping (section → Symbol)

| `Symbol` field | Value for a markdown section |
|---|---|
| `kind` | `"section"` |
| `language` | `"markdown"` |
| `name` | heading text, raw inline (e.g. `Phase 1 — intra-file edges`) |
| `qualified_name` | heading path joined by ` > ` — e.g. `Phased plan > Phase 1 — intra-file edges` |
| `signature` | the raw heading line including markers — e.g. `## Phase 1 — intra-file edges` |
| `byte_offset` / `byte_length` | the `section` node's span (heading → end of subtree) |
| `line` / `end_line` | derived from byte offsets, same as code path |
| `docstring` | first non-empty paragraph of the section body, truncated (orientation aid in `outline`) |
| `content_hash` | `sha256` of the section bytes — reused for incremental change tracking |
| `keywords` | prose tokenisation of the heading text (split on non-alphanumeric, lowercase, drop len≤1) — *not* `_name_words`, which is camel/snake-oriented |
| `decorators` / `param`/`return` | empty (default) |

### Heading-path separator: ` > `, not `.`

Code symbols use `.` (`MyClass.method`). Markdown headings contain dots and spaces, so `.` would be ambiguous and ugly. We use ` > `. `qualified_name` is treated as an **opaque string** downstream — the id is built by interpolation (`cli.py:104`) and nothing splits it on `.` — so the separator choice is free. *(Verified.)*

### Edge cases (decided)

- **Frontmatter (`minus_metadata`):** not emitted as a symbol. If it contains a `title:`, we *may* use it as the `name` of a synthetic file-level section when the doc has no H1 (deferred — see Open questions).
- **Preamble** (content before the first heading): emitted as a single `section` named `"(preamble)"` only if it contains non-trivial text; otherwise skipped. Keeps lead-in prose reachable without polluting the outline.
- **No-heading file** (flat notes): the whole file becomes one `section`, named from the frontmatter `title` if present, else the filename stem.
- **Duplicate headings** (two `## Overview` under the same parent): identical `qualified_name` → identical id → existing `_disambiguate` appends `~N`. Reuse, no new logic.
- **Inline markup in headings** (`## The \`code\` thing`): `name` keeps the raw inline text (backticks included). Stripping is deferred; raw is unambiguous and cheap.

### Scope: which files

**All `.md` and `.markdown`** in the repo, subject to the existing filters (`.gitignore`, `SKIP_DIRS`). Add both suffixes to `EXTENSION_MAP` so `_should_skip_file` admits them and `language_counts` reports them. No markdown-specific exclusions.

> Note: `SKIP_DIRS` already excludes `tests`/`__tests__`, so fixture markdown under those won't be indexed — acceptable.

## Integration points (all verified)

1. `parser/languages.py` — add `".md"` and `".markdown"` to `EXTENSION_MAP` (value `"markdown"`); define `MARKDOWN_SUFFIXES`.
2. `parser/extractor.py` — add `parse_markdown()`; dispatch on suffix at the top of `parse_file`.
3. **Nothing else.** `cmd_index`'s walk, `_should_skip_file`, storage, the sources mirror, and `outline`/`get`/`search`/`grep`/`stats` all consume `Symbol`/`kind` generically.

## Downstream behaviour (unchanged commands, verified)

- `loci outline --file docs/design/X.md` → the heading tree as symbols, each with an id.
- `loci get <id>` → the full section body (heading → end of subtree).
- `loci search "cross-file resolution" --kind section` → headings/sections matching, filterable by the new kind.
- `loci stats` → reports `markdown` in `language_counts`.

This realises the agent workflow per the *Agentic Tool Design* rule: `outline` returns the section IDs that `get` consumes — no extra calls.

## Alignment with the graph layer

This lands the **node substrate** for markdown ahead of the in-flight graph layer (`2026-06-10-graph-layer-design.md`). Sections carry the same `id`/`qualified_name` shape as code symbols, so the graph layer's **Phase 1 `contains` edge** (parent heading → child heading) drops on for free, entirely intra-file — zero cross-file fabrication risk, the exact class the graph design ships first. Markdown link references (`[text](#anchor)` / `[text](other.md)`) are a natural future `references` edge but are **out of scope here** and explicitly deferred to the graph work.

## Testing strategy

`tests/` (pytest, matching the existing suite). New `test_markdown_extraction.py`:

- **Nesting:** H1>H2>H3 produces three sections with the correct ` > ` qualified-name paths and parent/child byte containment.
- **Byte spans:** a section's `get` body runs from its heading through the end of its deepest subsection, and stops at the next same-or-higher heading.
- **Edge cases:** frontmatter skipped; preamble captured/skipped per rule; no-heading file → one section named from title/stem; duplicate sibling headings → `~N` disambiguation.
- **Field mapping:** `kind="section"`, `language="markdown"`, `signature` = raw heading line, `docstring` = first paragraph, `keywords` prose-tokenised.
- **Integration:** index a fixture repo with a `.md`, assert `outline`/`get`/`search --kind section` round-trip the section and its body.
- **Determinism:** re-indexing an unchanged `.md` yields identical `content_hash` (incremental path is a no-op).

TDD: failing tests first, then `parse_markdown`.

## Boundaries

**Always:**
- Return the existing `Symbol` dataclass unchanged — no schema changes for markdown.
- Keep the code extraction path untouched; markdown is a parallel branch.
- Respect existing file filters (`.gitignore`, `SKIP_DIRS`, `SKIP_FILES`).

**Ask first:**
- Adding any new `Symbol` field for markdown (e.g. heading level as a first-class field).
- Indexing markdown link targets as edges (belongs to the graph-layer doc, not here).
- Any change to `outline`/`get` output shape.

**Never:**
- Pull in `markdown_inline` or any new dependency for this feature.
- Emit a section whose byte span doesn't round-trip through `get`.
- Special-case the generic `_walk`/`LanguageSpec` machinery for markdown.

## Open questions (for review)

1. **`docstring` = first paragraph** — useful orientation in `outline`, or noise? Alternative: leave empty and let `signature` (the heading line) carry it.
2. **Frontmatter `title`** — worth surfacing as a synthetic file-level section when no H1 exists, or ignore frontmatter entirely?
3. **Setext headings** (`===`/`---` underlines) — the grammar emits `setext_heading`; handle alongside `atx_heading`, or ATX-only for v1? (Repo docs are ATX throughout, so ATX-only is low-risk.)
