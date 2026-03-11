# Auto-Summarize Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make symbol summarization automatic after `loci index` by creating a focused Haiku subagent prompt and updating the loci skill to make the step non-optional.

**Architecture:** Two file changes only — no loci code changes. A new `summarizer-prompt.md` file holds the Haiku subagent prompt and all summary rules. The existing `SKILL.md` replaces its optional "Summaries Workflow" hint with a mandatory indexed workflow that dispatches the Haiku subagent and applies results.

**Tech Stack:** Skill files only (Markdown). Haiku model ID: `claude-haiku-4-5-20251001`.

---

## Chunk 1: Summarizer prompt + skill update

### Task 1: Create the Haiku summarizer subagent prompt

**Files:**
- Create: `~/.claude/skills/loci/summarizer-prompt.md`

- [ ] **Step 1: Create `summarizer-prompt.md`**

Create `~/.claude/skills/loci/summarizer-prompt.md` with the following content:

```markdown
# loci Symbol Summarizer

You are a code symbol summarizer. You receive a batch of code symbols and return one-line summaries for each.

## Input

A JSON array of symbols:

```json
[
  {"id": "src/foo.py::bar", "signature": "def bar(x: int) -> str", "docstring": "Convert x to string."},
  {"id": "src/foo.py::Baz", "signature": "class Baz:", "docstring": ""},
  {"id": "src/foo.py::MAX_RETRIES#constant", "signature": "MAX_RETRIES = 3", "docstring": ""}
]
```

## Output

Return ONLY a raw JSON object mapping IDs to summaries. No markdown fences. No explanation. No other text.

```json
{
  "src/foo.py::bar": "Converts integer x to formatted string representation",
  "src/foo.py::Baz": "Base class for HTTP response handlers",
  "src/foo.py::MAX_RETRIES#constant": "Maximum number of retry attempts"
}
```

## Summary Rules

- ≤15 words per summary
- Action-oriented: start with a verb or noun phrase
- Never write "This function...", "This class...", "This method..."
- If docstring is present and informative: distill it into ≤15 words
- If docstring is absent, empty, or uninformative (e.g. "TODO", a single word that restates the name): infer from the signature, name, and kind alone
- For constants: describe what the value represents, not just its type
- Output ONLY the raw JSON object — no markdown code fences, no preamble, no trailing commentary

## Error Recovery

If you are unsure about a symbol, write the best one-line inference you can. Never omit an ID from the output — every input ID must appear in the output.
```

- [ ] **Step 2: Verify the file was created**

```bash
cat ~/.claude/skills/loci/summarizer-prompt.md | head -5
```
Expected: first line is `# loci Symbol Summarizer`

- [ ] **Step 3: Commit**

```bash
git -C ~/.claude add skills/loci/summarizer-prompt.md
git -C ~/.claude commit -m "feat: add loci Haiku summarizer subagent prompt"
```

If `~/.claude` is not a git repo, skip the commit step and note this in your report.

---

### Task 2: Update SKILL.md to make summarization mandatory

**Files:**
- Modify: `~/.claude/skills/loci/SKILL.md`

- [ ] **Step 1: Read the current SKILL.md**

Read `~/.claude/skills/loci/SKILL.md` and locate the `## Summaries Workflow` section. It currently reads:

```
## Summaries Workflow

`loci summarize <path>` outputs symbols with empty summaries. Dispatch a Haiku subagent to generate one-line summaries, write them to a JSON file `{"<id>": "<summary>"}`, then `loci summarize <path> --apply <file>`.
```

- [ ] **Step 2: Replace the Summaries Workflow section**

Replace that section with:

```markdown
## Summaries Workflow (mandatory after index)

After every `loci index`, run:

```bash
loci summarize <path>
```

If the output is a non-empty JSON array, summarization is **required** — not optional:

1. Split the array into chunks of 200 symbols
2. For each chunk: dispatch a Haiku subagent using `summarizer-prompt.md` in this skills directory, passing the chunk as inline JSON. Use `Agent` tool with `subagent_type=general-purpose`, `model=haiku` (model ID: `claude-haiku-4-5-20251001`)
3. If subagent returns malformed JSON: retry once with the reminder "Return only a raw JSON object, no markdown". If still malformed: skip the chunk and continue
4. Merge all chunk results into a single dict
5. Write to `/tmp/loci-summaries-<pid>.json`
6. Run: `loci summarize <path> --apply /tmp/loci-summaries-<pid>.json`
7. Delete the temp file

If `loci summarize` returns an empty array (all symbols already summarized), skip all the above steps.
```

- [ ] **Step 3: Also update the command table**

In the `## All Commands` table, update the summarize rows from:

```
| `loci summarize <path>` | Getting unsummarized symbols to fill via Haiku subagent |
| `loci summarize <path> --apply <file>` | Storing generated summaries back |
```

to:

```
| `loci summarize <path>` | Check for unsummarized symbols (run after every index) |
| `loci summarize <path> --apply <file>` | Write generated summaries back (used by Summaries Workflow) |
```

- [ ] **Step 4: Verify the change looks correct**

```bash
grep -A 20 "Summaries Workflow" ~/.claude/skills/loci/SKILL.md
```
Expected: the new mandatory workflow text appears.

- [ ] **Step 5: Commit**

```bash
git -C ~/.claude add skills/loci/SKILL.md
git -C ~/.claude commit -m "feat: make summarization mandatory in loci skill workflow"
```

If `~/.claude` is not a git repo, skip the commit step and note this in your report.

---

### Task 3: Smoke test on a real repo

- [ ] **Step 1: Run summarize on the loci repo itself**

```bash
loci summarize /home/brummerv/exploration/loci | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'{len(d)} unsummarized symbols')"
```
Expected: a count of unsummarized symbols (may be 0 if previously summarized, may be many if not).

- [ ] **Step 2: If count > 0, run the full workflow manually**

Take the first 3 symbols from the output and dispatch a Haiku subagent using `summarizer-prompt.md` to verify the prompt produces valid output.

Pass these 3 symbols to the subagent exactly as specified in `summarizer-prompt.md`. Verify:
- Output is valid JSON
- Every input ID is present in the output
- Each summary is ≤15 words
- No "This function/class" prefixes

- [ ] **Step 3: Report results**

Report whether the Haiku subagent produced valid, well-formed summaries. If not, note what went wrong so the prompt can be improved.
