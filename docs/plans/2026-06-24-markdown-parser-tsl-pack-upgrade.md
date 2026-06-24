# Plan: fix markdown indexing at latest `tree-sitter-language-pack` (+ fail loud)

**Status:** implemented in loci · **Author:** drafted from a flowmap session that hit this · **Date:** 2026-06-24

This plan was actioned in loci. It is self-contained: problem, root cause,
exact scope, the verified fix, the correctness gate, and done criteria are all below.

---

## TL;DR

`loci`'s markdown extractor (`parse_markdown` in `src/loci/parser/extractor.py`) builds its
parser with `tree_sitter_language_pack.get_parser("markdown")` and calls `.parse(source_bytes)`.
On **`tree-sitter-language-pack` 1.10.7** (current latest) that call **raises**
`TypeError: 'bytes' object is not an instance of 'str'`, and the function's blanket
`except Exception: return []` **swallows it silently** — markdown files index to zero symbols,
no error, exit 0. Code parsing is unaffected (it uses the high-level `process()` API).

Two changes:
1. **Fix forward to the new API.** Build the markdown parser with the classic `tree_sitter`
   API seeded from `get_language("markdown")` instead of `get_parser("markdown")`. Verified to
   work at 1.10.7, takes bytes, and preserves the classic Node API the existing walker relies on
   — so the walker helpers need **no** changes.
2. **Fail loud.** Replace the silent `except: return []` so a parse failure (or a non-empty
   markdown file that yields zero symbols) surfaces instead of rotting quietly.

---

## Why this matters / how it was found

A downstream tool (`~/improvements/flowmap`) imports `loci.service` in-process for drift
checking. Its markdown drift-checks silently passed-as-empty. Root-caused to: a fresh
`uv pip install -e ~/loci` into a new venv resolved `tree-sitter-language-pack==1.10.7`
(loci pins only `>=0.7.0`), whereas loci's own `.venv` has `0.13.0`. The 1.10.7 grammar binding
changed the parse API; loci's markdown path never adapted. flowmap currently carries a
**stopgap pin** (`tree-sitter-language-pack==0.13.0`) that must be removed once this lands
(see "Downstream cleanup").

The decision (with the repo owner): **fix forward to latest** — do not pin loci backward. A
parse-tree tool should track the grammar and adapt its extractors, and it must fail loud when a
grammar bump breaks an extractor.

---

## Reproduce first (throwaway venv, do not disturb `~/loci/.venv`)

```bash
cd /tmp && rm -rf locimig && uv venv --python 3.14 locimig
VIRTUAL_ENV=/tmp/locimig uv pip install -e ~/loci pytest
/tmp/locimig/bin/python -c "import importlib.metadata as m; print(m.version('tree-sitter-language-pack'))"  # expect 1.10.7+
cd ~/loci && /tmp/locimig/bin/python -m pytest -q    # expect ~17 failures, all markdown
```

Expected baseline failure set (17): all of `tests/parser/test_markdown.py` (13) plus 4 in
`tests/test_cli.py` (`test_stats_splits_code_and_docs`, `test_stats_outlines_split_by_language`,
`test_stats_pretty_shows_doc_lane`, `test_stats_file_read_of_markdown_lands_in_docs_lane` —
these depend on markdown landing in the "docs" lane). The other 184 pass: **code parsing is not
affected**, only markdown.

Confirm the swallowed error directly:
```bash
/tmp/locimig/bin/python -c "
from tree_sitter_language_pack import get_parser
get_parser('markdown').parse(b'# x')   # TypeError: 'bytes' object is not an instance of 'str'
"
```

---

## Root cause (confirmed facts about 1.10.7)

In `src/loci/parser/extractor.py::parse_markdown`:
```python
from tree_sitter_language_pack import get_parser
parser = get_parser("markdown")
tree = parser.parse(source)          # source is bytes (path.read_bytes())
...
except Exception:
    return []                        # <-- swallows the TypeError
```

At `tree-sitter-language-pack==1.10.7` (with `tree-sitter==0.25.2`):
- `get_parser("markdown").parse(bytes)` → **`TypeError` (wants `str`)**.
- `get_parser("markdown").parse(str)` → returns a tree, **but** `tree.root_node` is now a
  **callable** (method, not property) and the resulting native `builtins.Node` has **no `.type`
  attribute**. So you cannot just "decode to str and keep walking" — the low-level Node API of
  the object `get_parser` returns has changed shape. (This is why the code path abandoned
  low-level walking for the high-level `process()` API — see `_parse_file_with_process`.)

## The fix (verified at 1.10.7)

Construct the markdown parser with the **classic `tree_sitter` API**, seeding the language from
`tree_sitter_language_pack.get_language("markdown")`. This returns classic `tree_sitter` `Tree`/
`Node` objects: `root_node` is a property, `.type` / `.children` / `.start_byte` / `.end_byte`
all exist, and it accepts **bytes**. Byte offsets index UTF-8 bytes correctly (verified with a
`# Café` heading — the 2-byte `é` slices and decodes correctly).

Replace only the parser-construction lines in `parse_markdown`:
```python
# was:
#   from tree_sitter_language_pack import get_parser
#   parser = get_parser("markdown")
#   parse = getattr(parser, "parse", None)
#   if parse is None: return []
#   tree = parse(source)
from tree_sitter import Parser
from tree_sitter_language_pack import get_language
parser = Parser(get_language("markdown"))
tree = parser.parse(source)          # source stays bytes — do NOT decode
```
Everything downstream (`_walk_md_section`, `_md_heading_node`, `_md_heading_text`,
`_md_heading_line`, `_md_first_paragraph`, `_append_md_symbol`) is **unchanged** — it uses the
classic Node API this preserves, and keeps slicing the original `source` bytes by byte offset.

Verified snippet (this is exactly what the fix does, and it passes):
```python
from tree_sitter import Parser
from tree_sitter_language_pack import get_language
data = b"# Caf\xc3\xa9\n\nbody\n"
tree = Parser(get_language("markdown")).parse(data)
assert tree.root_node.type == "document"
# section -> atx_heading -> inline; byte offsets slice the bytes correctly
```

> Optional hardening (decide during implementation, don't over-reach): `parse_file`'s low-level
> first-try (`get_parser(spec.ts_language).parse(source_bytes)`) also throws at 1.10.7 and falls
> through to `_parse_file_with_process` (which works). That fallback masks the same API break for
> code. It's functional today, so leave it unless you want consistency — if you do, the same
> `Parser(get_language(...))` construction works there too. Keep this out of scope unless trivial.

## Fail loud (agreed requirement)

The silent `except Exception: return []` in `parse_markdown` is the reason this rotted unnoticed.
Change it so a future grammar/API break is **noisy**:
- Do **not** blanket-swallow. Catch only the narrow expected I/O case (`OSError`/`PermissionError`
  on read). Let a parse/API error propagate, or log it at `WARNING`/`ERROR` with the file path
  and re-raise / surface a structured warning that `index_repo` already collects
  (`zero_symbol_warnings` exists — reuse that channel).
- Add a guard: if a markdown file has non-whitespace content but `parse_markdown` returns **zero**
  symbols, that is suspicious — emit a warning (same `zero_symbol_warnings` mechanism used
  elsewhere in `index_repo`). This is the tripwire that pages a human on the next grammar bump.
- Mirror the principle anywhere else an extractor swallows exceptions into `return []`.

## Tasks (ordered)

1. Reproduce (above); confirm the 17-failure baseline and the `TypeError`.
2. Apply the parser-construction fix in `parse_markdown`.
3. Implement fail-loud (narrow except + zero-symbol-on-nonempty warning).
4. Run `pytest -q` at latest in the throwaway venv → all green (the 17 fixed, 0 regressions).
5. Add a unicode byte-offset regression test (`# Café` heading + a multibyte body) asserting the
   section symbol's `byte_offset`/`byte_length`/`line` are correct — locks in the offset semantics.
6. Add a test that a parse/API failure is **surfaced, not swallowed** (e.g. monkeypatch the parser
   to raise and assert a warning/exception, not a silent `[]`).
7. Re-confirm in `~/loci/.venv` (bump it to latest too): `uv pip install -e .` then `pytest`.
8. Optionally raise loci's `tree-sitter-language-pack` floor in `pyproject.toml` to the lowest
   version you've verified, but do **not** cap it — the point is to track latest.

## Done criteria

- [x] `loci`'s full test suite passes with `tree-sitter-language-pack` at **latest** (1.10.7+).
- [x] Markdown indexes correctly via `loci index` / `loci outline` / `loci grep` (sections as
      symbols, content grep-able), confirmed on a real `.md` with a unicode heading.
- [x] A parse/API failure or a non-empty-file-yields-zero-symbols case **surfaces** (log/warn/raise),
      proven by a test.
- [x] New unicode byte-offset regression test passes.
- [x] `~/loci/.venv` green.

## Downstream cleanup (after this lands)

`~/improvements/flowmap/pyproject.toml` carries a stopgap:
```toml
"tree-sitter-language-pack==0.13.0",   # STOPGAP (with a comment pointing here)
```
Once loci works at latest, **remove that pin** from flowmap, `uv pip install -e ".[dev]"`, and run
flowmap's suite (`pytest -q`) — its markdown drift-check test must still pass on the latest grammar.
That removal is the signal this migration is fully closed.
```bash
# in ~/improvements/flowmap after loci is fixed + reinstalled:
#   - delete the tree-sitter-language-pack==0.13.0 line (and its STOPGAP comment) from pyproject.toml
#   - uv pip install -e ".[dev]" && .venv/bin/python -m pytest -q
```
