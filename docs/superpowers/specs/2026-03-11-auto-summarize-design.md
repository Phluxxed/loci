# loci Auto-Summarize Design Spec

**Date:** 2026-03-11
**Status:** Approved

## Purpose

Eliminate the manual summarize step after `loci index`. Summaries serve two purposes: letting me decide whether to fetch a symbol from `outline` output, and enriching search ranking. Currently the skill documents the pattern but doesn't enforce it and provides no subagent prompt — so summaries never actually get filled.

## Deliverables

Two files, no loci code changes:

1. `~/.claude/skills/loci/summarizer-prompt.md` — Haiku subagent prompt (contains all rules)
2. `~/.claude/skills/loci/SKILL.md` — updated to make summarization non-optional after index; references `summarizer-prompt.md`

---

## Haiku Summarizer Subagent

**File:** `~/.claude/skills/loci/summarizer-prompt.md`

All summary rules live here. SKILL.md's index workflow section points to this file rather than restating the rules.

### Dispatch mechanism

Dispatched via the Claude Code `Agent` tool with `subagent_type=general-purpose` and `model=haiku` (model ID: `claude-haiku-4-5-20251001`). The controller (skill) passes the batch as inline JSON in the prompt — no file reads required.

### Input format

```json
[
  {"id": "src/foo.py::bar", "signature": "def bar(x: int) -> str", "docstring": "..."},
  {"id": "src/foo.py::Baz", "signature": "class Baz:", "docstring": ""}
]
```

### Output format

The subagent must return **only** a JSON object — no markdown fences, no explanation:

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
- If docstring is present and informative: distill it
- If docstring is absent, empty, or uninformative (e.g. "TODO", single-word restatement of the name): infer from signature, name, and kind alone
- Output ONLY the raw JSON map — no explanation, no markdown wrapper, no code fences

### Batching

`loci summarize <path>` outputs only symbols with empty summaries, so incremental re-indexes naturally skip already-summarized symbols.

Chunks of 200 symbols per subagent call (conservative estimate to stay within Haiku context budget; may need tuning for repos with verbose signatures/docstrings).

The controller merges results from all chunks into a single in-memory dict (last-write-wins for any duplicates, which should not occur). Results are written to a temp file (`/tmp/loci-summaries-<pid>.json`), then applied with `loci summarize <path> --apply <tmpfile>`. The temp file is deleted after apply.

### Error handling

If a subagent call returns malformed JSON or a non-object (e.g. wrapped in markdown, returned as array):
1. Retry once with an explicit reminder: "Return only a raw JSON object, no markdown"
2. If still malformed: skip that batch and log a warning; do not abort the entire summarize run

---

## Skill Update

**File:** `~/.claude/skills/loci/SKILL.md`

Replace the `## Summaries Workflow` section with the mandatory index flow:

```
1. loci index <path> [--incremental]
2. loci summarize <path>
   → if non-empty: dispatch Haiku summarizer (see summarizer-prompt.md), chunked at 200
   → merge results, loci summarize <path> --apply <tmpfile>, delete tmpfile
3. Continue with outline → get
```

Steps 2-3 are skipped only when `loci summarize` returns an empty array. Otherwise required.
