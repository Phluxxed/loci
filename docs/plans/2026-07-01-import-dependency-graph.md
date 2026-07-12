# Plan: import / dependency graph capability for loci

**Status:** ready to action · **For:** a fresh session in `~/loci`, end-to-end · **Date:** 2026-07-01 (v2 — rewritten after an adversarial review against the real source caught a repo-wide breaking change, an incoherent extraction recipe, a Go nesting miss, a hand-waved resolver, and a stale-index trap).

Self-contained. TDD — mirror the existing per-language extractor + service + MCP + CLI test patterns. Run `pytest -q` after each layer; the suite must stay green. This adds a **resolved, in-repo import/dependency graph** to loci, extracted from tree-sitter parse trees (not text grep), exposed via service + MCP + CLI.

## Why (the consumer + the bar)

`~/improvements/flowmap` needs a trustworthy cross-file dependency graph to measure how completely an inferred data-lineage map covers the code's real structure. `loci_grep` of symbol names is biased and noisy (misses aliased/attribute deps, collides same-named symbols across a monorepo, needs a keyword stoplist). Resolving imports from the parse tree loci already builds fixes all of that. Also generally useful (architecture views, blast-radius, dead-file detection).

**Bar:** edges are *resolved* (specifier → an actual indexed file); same-named symbols in different files never collide; anything unresolvable is **reported, never silently dropped**; adding the feature **breaks no existing call site** and **does not silently return empty on already-indexed repos**.

## Scope (v1)

- **File-level, in-repo, per-statement edges.** For each import (and JS/TS re-export — see below) in an indexed file, emit an edge to the indexed file it resolves to. Resolution is scoped to the **set of indexed files** — external deps (stdlib, npm, crates) are not edges; they're reported as `unresolved`.
- **Languages resolved:** Python, TypeScript, TSX, JavaScript. **Go/Rust:** extract-and-report (resolution best-effort; unresolved is acceptable and documented).
- **JS/TS re-exports** (`export * from './x'`, `export {y} from './x'`) ARE captured — barrel files are real cross-file wiring. (This was an out-of-scope gap in v1; pulled in because flowmap's real targets are TS-heavy.)
- **TS `import type`** is captured but **flagged** `type_only: true` so consumers can exclude type-only deps (they're not data flow).
- **Out of scope (document as limitations, don't build):** symbol-to-symbol resolution (file-level only); TS `tsconfig` `paths`/`baseUrl` aliases; `go.mod`/`Cargo.toml` module-root resolution; dynamic `import()`/`require()` with non-literal specifiers; following re-export *chains* to an original definition; Python `TYPE_CHECKING`-guarded imports (captured as normal imports — not distinguishable cheaply). Unresolved specifiers are reported.

## Architecture (verified insertion points)

### 1. Extract imports — a NEW standalone function, NOT a change to `parse_file`

**Do not change `parse_file`'s signature.** It returns `list[Symbol]` and is consumed as a bare list in `service.py:111` and ~50 test call sites (`tests/parser/test_extractor.py`, `tests/parser/test_markdown.py`, `tests/test_cli.py`, and the `lambda path: []` monkeypatch in `tests/test_service.py:60`). Changing its return type is a repo-wide break. Instead add a **separate** `extract_imports(path: Path) -> list[RawImport]` in `src/loci/parser/extractor.py` with its own parse.

- **Its own parse, one coherent path.** Build the parser the fixed-markdown way (commit `fb34854`): `Parser(get_language(spec.ts_language))`; parse bytes; do **not** reuse `_add_python_constants`/`_add_javascript_constants` (those use `ast`/regex — a different mechanism; the earlier plan's "mirror them and walk the tree" was incoherent). If parsing fails, return `[]` for that file and record a structured warning (reuse `zero_symbol_warnings`-style surfacing) — never swallow silently.
- **Recursively scan** the tree for the language's import node types (a plain recursive descent collecting matching nodes). Recursion is required: Python/JS/TS/Rust import nodes are top-level children, but **Go `import_spec` is nested** under `import_declaration` → `import_spec_list` (verified) — a shallow top-level scan misses every Go import.
- **Node types per language** (all verified against `tree_sitter_language_pack`):
  - Python: `import_statement`, `import_from_statement`
  - JS/TS/TSX: `import_statement`; **plus `export_statement` that has a `from`/`source` child** (re-exports)
  - Go: `import_spec` (nested — see above) · Rust: `use_declaration`
- **`RawImport`** = `{source_relpath, line, text, specifier, imported_names, type_only, is_reexport}`. `specifier` is the raw module string (`"a.b"`, `"./foo"`, `"../core"`). `type_only` = true for TS `import type …` / `import { type X }` (the node carries a `type` keyword child). `is_reexport` = true for `export … from`.
- **Where to put per-language node-type config:** add an optional `import_node_types` mapping to `LanguageSpec` (`languages.py:6–17`) and populate it in `_SPECS` (`languages.py:19–115`). **Put TS import types on the `typescript` spec, not the `tsx` spec** — `EXTENSION_MAP[".tsx"] = "typescript"` (`languages.py:127`), so the standalone `tsx` spec is never selected for parsing.

### 2. Resolve specifiers — NEW `src/loci/parser/resolver.py`

`resolve_import(source_relpath, specifier, imported_names, language, indexed_files: set[str]) -> str | None`. Pure (path arithmetic only), resolves **against `indexed_files`**. **The algorithm is specified, not gestured at:**

**Python.** Let the importing file's package dir = `dirname(source_relpath)`.
- **Relative** (`specifier` is empty/None with N leading dots, or `from . import x`): N dots ⇒ base = importing dir walked up `N-1` levels (1 dot = importing dir). Append the (possibly empty) dotted remainder as path segments to get module base `B`.
- **Absolute** (`import a.b.c` / `from a.b.c import …`): module base `B = "a/b/c"` from the dotted specifier.
- Resolve module base `B` to a file: try **`B.py` before `B/__init__.py`**; if neither in `indexed_files`, unresolved.
- **`from M import N` disambiguation** (the risky case): if `M` resolved to a package (`M/__init__.py`) or dir, and `N` names a submodule — try **`M_dir/N.py` before `M_dir/N/__init__.py`**; if that submodule file is indexed, the edge target is the **submodule** (`c` is a module). Otherwise the target is **`M`'s file** (`c` is a symbol defined in module `M`). Submodule check first, symbol fallback second.
- **`import a.b.c.d`**: **one** edge, to the deepest resolvable file (`a/b/c/d.py|/__init__.py`); do **not** emit edges to intermediate packages.

**JS/TS/TSX.** Only relative specifiers (`./`, `../`) are in-repo; bare (`react`) ⇒ unresolved. Resolve the relative path against `dirname(source_relpath)`, then try in this exact order (**file before directory-index**, matching Node): `p.ts, p.tsx, p.js, p.jsx, p.mjs, p.cjs`, then `p/index.{ts,tsx,js,jsx,mjs,cjs}`. First match in `indexed_files` wins; one edge; else unresolved.

**Go/Rust.** Best-effort: if the specifier trivially maps to an indexed file, edge; else unresolved. Acceptable for v1.

**Multiple candidates:** the fixed order above is the tie-break, and it is the contract — document it so two implementers produce identical graphs.

### 3. Store on the index — `src/loci/storage/index_store.py`

- Add a top-level `imports` list to `index.json`: `[{source, target, line, text, type_only, is_reexport}]` (`target` null when unresolved → goes to the `unresolved` view). Add a **`schema_version`** int to the index (there is none today — verified). Bump it for this feature.
- **`write()` signature** is fixed positional `(repo_path, symbols, file_hashes)` (`index_store.py:63`). Add an `imports` parameter and persist it. Add a read accessor `get_imports(file=None)`.
- **Stale-index safety (critical — else the downstream signal is silently empty):** on load, if `schema_version` is missing/older than this feature's, `index_repo` must treat the repo as needing a **full (non-incremental) reindex** so imports get populated — an already-indexed repo must not return an empty graph. `import_graph` must additionally read `index.get("imports", [])` defensively.
- **Incremental round-trip (must be specified — mirror the symbol path exactly):** the symbol path keeps unchanged files via `[Symbol.from_dict(s) for s in existing if s["file_path"] == rel]` (`service.py:104`). Do the identical thing for imports: `kept = [i for i in existing.get("imports", []) if i["source"] != rel_path]`, then re-extend with freshly extracted imports for the changed files, and pass the union to `write()`. Without this, an incremental run drops imports for untouched files.

### 4. Service — `src/loci/service.py`

Add after `analyze_usage()` (`~line 358`), matching the `dict`-return convention:

```python
def import_graph(repo, file=None) -> dict:
    # reads the on-disk index (IndexStore.load re-reads index.json each call), filters to `file` if given
    return {
        "edges":      [{"source","target","line","text","type_only","is_reexport"}],  # in-repo, resolved
        "unresolved": [{"source","line","text","specifier"}],                          # external/unresolvable
    }
```

Resolution happens at index time (step 2/3), so this is a read + shape. `line`/`text` are the consumer's edge evidence.

### 5. Expose via MCP + CLI

- **`src/loci/mcp_server.py`** — `loci_imports(repo, file=None)` `@mcp.tool()` via `_handle_loci_error` (`~line 137`), like `loci_outline`.
- **`src/loci/cli.py`** — `cmd_imports()` near `cmd_outline()` (`~line 582`) printing `json.dumps(result, indent=2)`, plus subparser + dispatch in `main()` (`~line 619`). Mirror `outline`.

## Tests (TDD; layout per existing `tests/`)

- **NEW `tests/parser/test_imports.py`** — extraction: fixtures yielding expected `RawImport`s for Python (`import`, `from…import`, relative), JS/TS (`import`, `import type` → `type_only`, `export … from` → `is_reexport`), and **Go (nested `import_spec` is found — guards C4)**. Add `tests/fixtures/sample_imports.{py,ts,go}`.
- **NEW `tests/parser/test_resolver.py`** — pure `resolve_import` tests (no I/O): Python `from a.b import c` picks submodule `a/b/c.py` when indexed, else symbol-in-`a/b.py`; relative `from ..core import x` dots→dir arithmetic; `import a.b.c.d` → single deepest edge; JS `./foo` extension+index order; bare specifier → None; specifier not in `indexed_files` → None; both-candidates-exist tie-break is deterministic.
- **NEW `tests/test_import_graph.py`** — integration: **fixtures written to `tmp_path`, NOT under `tests/`** (loci's `SKIP_DIRS` includes `tests` — `service.py:20` — so fixtures inside `tests/` are never indexed). Index a small multi-file repo; assert edge `b→a` with correct `line`/`text`; a stdlib import → `unresolved`; **same-named symbols in two unrelated files produce NO edge** (the key anti-grep property); a re-export produces an edge; incremental re-index keeps imports for untouched files; a pre-imports (old `schema_version`) index triggers a full reindex rather than an empty graph.
- Extend `tests/test_mcp_server.py`, `tests/test_cli.py`.

## Done criteria

- [ ] `loci imports --repo <r>` + `loci_imports` MCP tool return resolved in-repo edges (with `line`/`text`/`type_only`/`is_reexport`) + `unresolved`.
- [ ] `parse_file` signature unchanged; full existing suite green (no call-site breakage).
- [ ] Same-named symbols in different files never create edges; external imports reported not dropped; Go nested imports found.
- [ ] Python + TS/TSX/JS resolution per the specified algorithm; re-exports captured; `import type` flagged.
- [ ] Imports persist with a `schema_version`; a pre-feature index reindexes fully (no silent-empty); incremental keeps untouched files' imports.
- [ ] New behaviour covered by tests.

## Downstream

`~/improvements/flowmap` consumes `import_graph` for edge-coverage — see `~/improvements/flowmap/docs/plans/2026-07-01-edge-coverage-via-reference-graph.md` (land this first).
