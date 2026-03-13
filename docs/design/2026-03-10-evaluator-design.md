# loci Evaluator Design

**Date:** 2026-03-10
**Status:** Approved

## Problem

loci fails silently. If a language spec has wrong node types, or a file fails to parse, `symbols_indexed` looks fine but symbols are missing. There is no way to detect total failures (0 symbols from a non-trivial file) or partial failures (missing methods, wrong byte offsets) without manually inspecting output.

## Goal

Give the agent (Claude) the tools to detect when loci is broken and diagnose why, without requiring a human to notice something is off.

## Components

### 1. Index-time warnings

**Change:** `loci index` output gains a `warnings` list.

A warning is emitted for any file that:
- Has a known extension (i.e. loci has a language spec for it)
- Is non-trivial (>10 lines)
- Produced 0 symbols

**Output shape:**
```json
{
  "path": "/repo",
  "symbols_indexed": 47,
  "files_skipped": 2,
  "languages": {"python": 12},
  "warnings": [
    {"file": "src/big_module.py", "lines": 234, "reason": "0 symbols extracted"}
  ]
}
```

No warnings = silent success (current behaviour preserved). Warnings = I know to investigate.

### 2. `loci verify <repo>` command

On-demand spot-check. For each indexed symbol:
1. Read the stored byte offset from the index
2. Fetch the corresponding bytes from the cached source file
3. Re-parse the file with tree-sitter
4. Check the re-parsed symbol at that position matches name + kind in the index

Reports mismatches, missing symbols, and byte offset errors.

**Output shape:**
```json
{
  "repo": "/repo",
  "checked": 47,
  "passed": 45,
  "failed": [
    {
      "id": "abc123",
      "file": "src/foo.py",
      "name": "MyClass",
      "kind": "class",
      "issue": "byte_offset_mismatch"
    }
  ]
}
```

**Verification algorithm (intentional simplification):** Rather than a full tree-sitter re-parse (which would be circular — using the same parser that may be broken), verify uses a name-in-bytes check: fetch the stored byte range from the cached source, decode it, check the symbol's name appears in the text. This catches byte offset corruption and wrong-node-type extraction. It won't catch a symbol name coincidentally appearing in a comment at a wrong offset, which is an acceptable trade-off for the implementation cost.

**When to run:** After any language spec change, after a re-index, or when search results feel wrong.

### 3. Ground-truth test fixtures

Replace minimal `sample.py` / `sample.ts` with comprehensive fixtures that cover:
- Top-level functions and classes
- Methods within classes
- Decorated functions/classes
- Nested classes
- Type aliases / interfaces (TypeScript)
- Module-level constants (excluded — not symbols)

Each fixture has a corresponding `EXPECTED_SYMBOLS` constant in the test file listing exact `(name, kind)` pairs. Tests assert:
1. All expected symbols are present in outline output
2. `loci get <id>` returns source that contains the symbol name
3. No unexpected symbols (prevents over-extraction)

## Self-heal flow (agent workflow)

```
loci index <repo>
  → warnings? → loci verify <repo> → identify mismatch → fix spec → re-index
  → no warnings? → done

tests fail after spec change?
  → ground-truth fixtures pinpoint which symbol type broke
  → fix spec → tests pass → re-index
```

## Out of scope

- Nested `.gitignore` support
- Statistical anomaly detection across files
- Automatic spec repair
