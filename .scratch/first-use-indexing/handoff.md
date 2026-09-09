# Handoff: Loci first-use indexing

Date: 2026-09-09
Status: first-use initialization and read-only source copying fixed; direct and downstream checks pass

## Completion update

The source mirror now copies each distinct file path once. The read-only
multi-section storage regression reproduced the failure before the fix;
afterward all 62 storage tests and the fresh-process cold/warm MCP regression
passed. The original source bytes and mode remain unchanged.

The stricter no-model Anvil preflight now passes p01, r01, and c01, each with
delivered Loci indexed-section evidence and positive byteCost. Snapshot
immutability assertions passed; no model ran. See `result.md` for details and
`/private/tmp/brain-loci-cold-check-V55Z8q-updated/result.json` for the report.
The following blocker description records the pre-fix diagnosis.

## Outcome

A normal Loci retrieval request against a valid, readable, unindexed root should
create its index and complete the requested retrieval in the same call. The
consumer should not need a separate pre-index operation.

The initial `REPO_NOT_INDEXED` defect is fixed in the current checkout.
`ensure_fresh_index` now allows a missing index, validates the root, and builds
under the shared refresh lock after rechecking the store. Fresh compiler
processes resolve `loci-mcp` through the installed wrapper and editable venv to
this checkout; the follow-up failure below is not an old resident-server result.

The source-mirroring fix and acceptance described below are now complete.

## Resolved blocker: repeated copying of read-only files

On 9 September, all three current-code, cold-store W4 preflights progressed
past the former missing-index failure but returned `LOCI_PROVIDER_FAILED` and
no delivered Loci sections. The error is `Permission denied` on the temporary
Loci cache's `sources.tmp/CONVENTIONS.md`.

`src/loci/storage/index_store.py:268-279`, `IndexStore.write`, loops over
**symbols**, calling `shutil.copy2(src, dest)` for each symbol's file:

1. A snapshot Markdown file has multiple section symbols and mode `0400`.
2. The first copy succeeds and preserves that read-only mode on the cache file.
3. The next symbol from the same file triggers another copy to the same path.
   Overwriting the now-read-only destination raises `PermissionError`.

Both the real snapshot file and its cached copy were verified as `0400`; the
cache directory is writable and owned by the current user. A disposable
`copy2` reproduction also confirmed the mechanism. This is ordinary file-mode
handling, not a reason to relax the sandbox or make Brain snapshots writable.

Copy each distinct source path once when building the source mirror, preserving
the existing atomic replacement and snapshot immutability boundaries.

The no-model report is
`/private/tmp/brain-loci-cold-check-V55Z8q/result.json`; its `results` entries
point to the full per-case captures. All three checks failed. Hashes of the
original execution tree, control files, and live Brain were unchanged, and no
model ran. The c01 check reads its post-timeout isolated Brain, not a new
behavioural fixture. These temporary files may expire; the multi-section,
read-only fixture below is the durable reproduction specification.

## Original failure and consumer context

Before the first-use fix, `loci_search` requested `ensure_fresh=True`, but
`ensure_fresh_index` called `_load_required_index` before reaching refresh.
An absent index therefore raised `REPO_NOT_INDEXED` instead of being created.

The triggering consumer is `/Users/brummerv/llm-wiki`:

- `src/llm_wiki_core/providers/loci.py`,
  `LociMcpGateway._retrieve_session`, searches `context.wiki_root` directly.
  Its provider catches the failure and returns diagnostics without Loci section
  candidates.
- `src/llm_wiki_core/providers/loci_graph.py` explicitly indexes its graph mirror
  and handles a missing index with indexing/retry. That is a separate root.

The test workspace, graph mirror, and immutable Brain snapshot wiki are three
different indexing targets. Indexing the workspace or mirror does not index
the snapshot queried by section retrieval.

## Evidence and limits of the prior fix

Captured cases live under
`/Users/brummerv/phluxxed/brain-w4-followup-2026-09-08/execution/`.
Inspect `p01`, `r01`, and `c01`, especially their `captures/fresh/` host context,
result, and events. The p01/r01 section target was:

```text
<case>/state/brain-snapshots/anvil-brain-codex-w4-followup/snapshots/cc42243c659f7c79ebfa55dafbdbac184fb1eeadf2583568462c73828fa7d1ae/wiki
```

Fresh temporary-store deterministic replays reproduced the missing-index error.
Its absolute `details.repo` path also broke the downstream path-free packet
validator. A subsequent llm-wiki fix sanitizes failure metadata; retain that
fix and the validator. It repairs error serialization, not section retrieval.

The associated Anvil runner preflight originally accepted non-kernel evidence
from any provider, allowing a false pass while Loci contributed no sections.
It now requires delivered evidence with `provider == "loci"`,
`route == "indexed_section"`, and positive `byteCost`. Its eight focused tests
pass, and the three saved false-positive responses are now rejected. Text,
temporal, frontmatter, and graph evidence cannot substitute for Loci sections.

## Implementation and acceptance

1. Add a regression using a Markdown file with at least two indexed sections
   and mode `0400`, in a readable snapshot-shaped root with an empty Loci store.
   It must expose the repeated-copy failure before the storage fix.
2. Fix duplicate source copying in `IndexStore.write`. Verify multiple symbols
   from one file still retrieve correctly and the original bytes and mode are
   unchanged. Retain the completed first-use initialization fix.
3. Through a normal MCP retrieval, with no explicit index call, prove the cold
   index is created and the expected section is returned. Check a subsequent
   warm retrieval and the smallest directly relevant storage regressions.
4. After the direct checks pass, run the stricter Anvil cold-store no-model
   preflight against the updated checkout. Require actual delivered Loci
   indexed-section evidence; safe diagnostics or other-provider evidence do
   not establish recovery. Report direct Loci and downstream results separately.

End when the read-only source-mirroring fix and directly relevant acceptance
checks pass. No new runner framework or caller-specific pre-indexing is needed.

## Boundaries

Preserve existing unrelated worktree changes. Keep the captured W4 cases
immutable. Do not launch model runs, re-use consumed cases, change the live
Brain, or modify llm-wiki/Anvil as part of this Loci handoff without Vik's
direction. A disposable no-model consumer check may supplement the direct
Loci tests once the shared behavior is fixed.
