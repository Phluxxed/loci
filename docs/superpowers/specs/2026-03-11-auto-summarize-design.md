# loci Auto-Summarize Design Spec

**Date:** 2026-03-11
**Status:** Approved

## Purpose

Eliminate the manual summarize step after `loci index`. Summaries serve two purposes: letting me decide whether to fetch a symbol from `outline` output, and enriching search ranking. Currently the skill documents the pattern but doesn't enforce it and provides no subagent prompt — so summaries never actually get filled.

## Deliverables

Two files, no loci code changes:

1. `~/.claude/skills/loci/summarizer-prompt.md` — Haiku subagent prompt
2. `~/.claude/skills/loci/SKILL.md` — updated to make summarization non-optional after index

---

## Haiku Summarizer Subagent

**File:** `~/.claude/skills/loci/summarizer-prompt.md`

The subagent receives the raw JSON array from `loci summarize <path>` and returns a JSON object mapping symbol IDs to one-line summaries.

### Input format

```json
[
  {"id": "src/foo.py::bar", "signature": "def bar(x: int) -> str", "docstring": "..."},
  {"id": "src/foo.py::Baz", "signature": "class Baz:", "docstring": ""}
]
```

### Output format

```json
{
  "src/foo.py::bar": "Converts integer x to formatted string representation",
  "src/foo.py::Baz": "Base class for HTTP response handlers"
}
```

### Summary rules

- ≤15 words per summary
- Action-oriented: starts with a verb or noun phrase
- Never prefixed with "This function/class/method..."
- If docstring exists: distill it
- If no docstring: infer from signature, name, and kind alone
- Output ONLY the JSON map — no explanation, no markdown wrapper

### Batching

The skill splits `loci summarize` output into chunks of 200 symbols before dispatching. Large repos get multiple sequential subagent calls. Each call gets its own chunk; results are merged into a single JSON file before `--apply`.

---

## Skill Update

**File:** `~/.claude/skills/loci/SKILL.md`

The index workflow becomes a required 3-step sequence:

```
1. loci index <path> [--incremental]
2. loci summarize <path>        # check for unsummarized symbols
   → if non-empty: dispatch Haiku summarizer subagent (chunked at 200)
   → loci summarize <path> --apply <tmpfile>
3. Continue with outline → get
```

Steps 2-3 are skipped only when `loci summarize` returns an empty array (no new symbols to fill). Otherwise they are required — not suggested.

The skill section currently at line 74 ("Summaries Workflow") is replaced with the above mandatory flow.
