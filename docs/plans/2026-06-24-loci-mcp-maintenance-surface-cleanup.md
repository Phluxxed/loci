# Plan: MCP production surface plus human maintenance CLI

**Status:** in implementation
**Date:** 2026-06-24
**Scope:** loci MCP/CLI surface cleanup, stats store routing, agent diagnostics, summarize decision

## Overview

`loci` has crossed the line where MCP is the production agent interface. Keeping the old CLI
navigation implementation now creates drift: bugs can be fixed in service/MCP and remain in CLI,
or vice versa. The remaining CLI value is human/operator maintenance, especially `stats --pretty`
from a shell or tmux.

This plan keeps that human CLI value while moving agent-facing diagnostics into MCP, fixing the
`LOCI_BASE_DIR` store mismatch, and removing the stale `summarize` workflow after audit showed it
does not earn its complexity.

## Architecture decisions

- MCP remains the production agent surface for navigation: index, outline, search, get, file, grep,
  verify, list.
- The CLI is not a second navigation product. It should become a human/operator maintenance surface.
- `stats` stays as CLI because it is mainly for a human in tmux.
- `analyze` becomes an MCP tool because it is for agents to diagnose loci behavior.
- `summarize` is removed. Current evidence does not show useful populated summaries or meaningful
  ambiguous-search value.
- Store resolution must be explicit and consistent. `loci stats` must read the same store MCP writes
  to, unless the caller intentionally overrides it.

## Current evidence

- Existing MCP tools: `loci_index`, `loci_outline`, `loci_search`, `loci_get`, `loci_file`,
  `loci_grep`, `loci_verify`, `loci_list`.
- CLI-only maintenance commands before cleanup: `stats`, `analyze`, `summarize`, `invalidate`.
- Existing design docs already say MCP is production and CLI is legacy/debug/migration safety.
- `stats` can look broken when MCP writes to `$HOME/.codex/loci-index` but plain CLI defaults to
  `~/.codeindex`.
- `summarize` was originally intended to help humans/agents decide whether to fetch a symbol from
  `outline` and to enrich search ranking.
- Current audit: the Codex MCP store had 28 indexed repos, 16,766 symbols, and 0 non-empty
  summaries. The legacy store had 90 indexed repos, 9,587 symbols, and 0 non-empty summaries.
- Search scoring gives summary text only weak optional weight (`+5` exact summary match, `+1` per
  query word), and tests only covered CLI plumbing/fake application, not real ambiguous-search
  value.

## Task list

### Phase 1: Baseline and store routing

#### Task 1: Prove the current stats store mismatch

**Description:** Reproduce the mismatch between MCP store usage and plain CLI stats. Capture the
actual store paths used by MCP config, wrappers, and default `IndexStore`.

**Acceptance criteria:**
- [x] `codex mcp get --json loci` store env is recorded.
- [x] `loci stats --pretty` and `LOCI_BASE_DIR=<mcp-store> loci stats --pretty` behavior is compared.
- [x] The plan identifies whether the bug is only default store selection or also missing MCP event logging.

**Verification:**
- [x] Run `loci_stats` or equivalent MCP calls after a real MCP `search/get` once available.
- [x] Confirm `session.jsonl` is written in the expected MCP store.

**Dependencies:** None

**Files likely touched:** None for the probe

**Estimated scope:** XS

#### Task 2: Fix stats default store resolution

**Description:** Make human `loci stats` read the same store MCP writes to by default, while keeping
`LOCI_BASE_DIR` as an explicit override.

**Acceptance criteria:**
- [x] `LOCI_BASE_DIR` still wins when set.
- [x] Without `LOCI_BASE_DIR`, `loci stats` prefers the active agent MCP store when discoverable.
- [x] The chosen store is visible in JSON output or `--pretty` output so wrong-store diagnosis is easy.
- [x] Tests cover default, override, and no-store cases.

**Verification:**
- [ ] `.venv/bin/python -m pytest tests/test_cli.py -k stats`
- [ ] Manual tmux/shell check: `loci stats --pretty` shows the same events as the MCP store.

**Dependencies:** Task 1

**Files likely touched:**
- `src/loci/cli.py`
- `src/loci/storage/index_store.py` or a small shared store-resolution helper
- `tests/test_cli.py`

**Estimated scope:** S

### Phase 2: MCP-native maintenance diagnostics

#### Task 3: Add service-layer stats/analyze functions

**Description:** Move stats and analyze access behind service functions so MCP and any retained CLI
code do not reach into `IndexStore` independently.

**Acceptance criteria:**
- [x] Service exposes a stats function with `repo`, `since_days`, and all-time options.
- [x] Service exposes an analyze function with `repo` and `since_days`.
- [x] Service errors use `LociError` where appropriate.
- [x] Existing CLI behavior can call these functions rather than duplicating store logic.

**Verification:**
- [ ] `.venv/bin/python -m pytest tests/test_service.py`

**Dependencies:** Task 2

**Files likely touched:**
- `src/loci/service.py`
- `tests/test_service.py`

**Estimated scope:** S

#### Task 4: Add `loci_stats` and `loci_analyze` MCP tools

**Description:** Expose stats and analyze through MCP for agents. `loci_analyze` is the important
agent diagnostic; `loci_stats` gives the agent a lightweight usage readout and proves store
alignment.

**Acceptance criteria:**
- [x] MCP exposes `loci_stats`.
- [x] MCP exposes `loci_analyze`.
- [x] Outputs are structured JSON objects, no pretty formatting.
- [x] MCP tests verify both tools through a real stdio client.
- [x] `loci_analyze` findings are suitable for an agent to act on without reading CLI docs.

**Verification:**
- [ ] `.venv/bin/python -m pytest tests/test_mcp_server.py`
- [ ] Fresh-session smoke: call `loci_stats` and `loci_analyze` through MCP.

**Dependencies:** Task 3

**Files likely touched:**
- `src/loci/mcp_server.py`
- `tests/test_mcp_server.py`
- `README.md`
- `skills/loci/SKILL.md`

**Estimated scope:** M

### Phase 3: Summarize decision gate

#### Task 5: Audit whether summaries are currently useful

**Description:** Measure the current summary system before deciding whether to keep, rebuild, or
delete it.

**Acceptance criteria:**
- [x] Count how many indexed symbols currently have non-empty `summary`.
- [x] Confirm whether search ranking uses `summary` and how much weight it contributes.
- [x] Run before/after examples where summaries should help ambiguous search.
- [x] Check whether outline summaries materially help choose a symbol without fetching it.
- [x] Record a recommendation: delete.

**Verification:**
- [ ] Add or run focused tests around search ranking with summaries.
- [ ] Document examples that demonstrate real value or lack of value.

**Dependencies:** Tasks 1-4 can proceed independently; this is a decision gate before touching
summarize behavior.

**Files likely touched:**
- `src/loci/storage/index_store.py`
- `tests/storage/test_index_store.py`
- docs only unless a clear bug appears

**Estimated scope:** S

#### Task 6A: If summarize is kept, make it MCP/service-native

**Description:** Keep summarize only as an explicit agent maintenance workflow. The CLI should not be
the authoritative implementation.

**Acceptance criteria:**
- [ ] Service functions list unsummarized symbols and apply summaries.
- [ ] MCP exposes maintenance tools with explicit names, for example `loci_summaries_pending` and
  `loci_apply_summaries`.
- [ ] The agent skill documents when to run the workflow and when to skip it.
- [ ] The summarizer prompt remains a reusable asset, not hidden CLI behavior.

**Verification:**
- [ ] Service tests for pending/apply behavior.
- [ ] MCP tests for pending/apply behavior.
- [ ] Search/outline tests prove summaries have value.

**Dependencies:** Task 5 with a "keep" decision

**Files likely touched:**
- `src/loci/service.py`
- `src/loci/mcp_server.py`
- `tests/test_service.py`
- `tests/test_mcp_server.py`
- `skills/loci/SKILL.md`
- `skills/loci/summarizer-prompt.md`

**Estimated scope:** M

#### Task 6B: If summarize is not useful, remove it

**Description:** Delete stale summarize commands, docs, tests, and workflow instructions so agents do
not spend effort maintaining dead machinery.

**Acceptance criteria:**
- [x] CLI `summarize` command is removed.
- [x] Summary-specific tests/docs/skill instructions are removed or rewritten.
- [x] Search ranking no longer gives misleading weight to missing summaries.
- [x] Existing indexes with `summary` fields remain harmless when loaded.

**Verification:**
- [x] Full test suite passes.
- [x] `rg "summarize|summarizer|apply_summaries"` returns only intentional historical docs or no hits.

**Dependencies:** Task 5 with a "delete" decision

**Files likely touched:**
- `src/loci/cli.py`
- `src/loci/storage/index_store.py`
- `tests/test_cli.py`
- docs/skills files

**Estimated scope:** M

### Phase 4: Retire CLI navigation duplication

#### Task 7: Define final CLI command set

**Description:** Decide and document the final CLI surface. Proposed final human CLI: `stats` only,
plus maybe `stats --reset`. Everything else is MCP or dev-only.

**Acceptance criteria:**
- [ ] Final CLI command list is explicitly documented.
- [ ] `analyze` is documented as agent/MCP-facing, not human CLI-facing.
- [ ] `invalidate` is either removed, made MCP-safe, or kept as a clearly marked dev/admin command.
- [ ] The help text matches the decision.

**Verification:**
- [ ] `loci --help` shows only the intended retained commands.

**Dependencies:** Tasks 2-6

**Files likely touched:**
- `src/loci/cli.py`
- `README.md`
- docs/design update or new ADR

**Estimated scope:** S

#### Task 8: Remove or thin-wrap CLI navigation commands

**Description:** Stop maintaining duplicate navigation implementations in `cli.py`. Either remove
navigation subcommands or convert temporary debug commands into thin wrappers over service functions.
The preferred endpoint is removal once MCP tools are visible in fresh sessions.

**Acceptance criteria:**
- [ ] No duplicate indexing loop remains in `cli.py`.
- [ ] CLI no longer defines independent `index/search/get/file/grep/outline/verify/list` behavior.
- [ ] MCP smoke tests cover the removed CLI behavior.
- [ ] CLI tests are reduced to retained human/operator commands.

**Verification:**
- [ ] `.venv/bin/python -m pytest`
- [ ] Fresh-session MCP smoke: `loci_index -> loci_outline/loci_search -> loci_get/loci_file -> loci_verify`.

**Dependencies:** Task 4 and a fresh session where MCP tools are visible

**Files likely touched:**
- `src/loci/cli.py`
- `tests/test_cli.py`
- `tests/test_mcp_server.py`
- README/skills docs

**Estimated scope:** M

### Phase 5: Docs, hooks, and migration cleanup

#### Task 9: Update docs and agent instructions

**Description:** Make the repo instructions reflect the final split: MCP for agents, CLI stats for
the human.

**Acceptance criteria:**
- [ ] README no longer presents CLI navigation as a normal workflow.
- [ ] The loci skill tells agents to use MCP and run `loci_analyze` when diagnosing tool quality.
- [ ] Human stats instructions include the store behavior and tmux-friendly examples.
- [ ] Historical design docs can remain, but current docs must not conflict.

**Verification:**
- [ ] `rg "CLI fallback|loci index|loci search|loci analyze"` in current docs returns only intended references.

**Dependencies:** Tasks 4, 7, 8

**Files likely touched:**
- `README.md`
- `skills/loci/SKILL.md`
- `.claude/skills/loci/SKILL.md`

**Estimated scope:** S

#### Task 10: Remove stale hook dependence on CLI indexing

**Description:** Older Codex/Claude hooks still mention or run CLI indexing. After MCP visibility is
verified, remove or rewrite those hooks so they do not preserve the CLI navigation surface by
accident.

**Acceptance criteria:**
- [ ] Codex/Claude setup docs do not install hooks that run `loci index` as the normal path.
- [ ] Any remaining hook is clearly optional and does not define production behavior.
- [ ] MCP setup has a concrete smoke check for success.

**Verification:**
- [ ] `codex mcp get --json loci`
- [ ] Fresh-session MCP smoke call.
- [ ] Hook tests updated or removed as appropriate.

**Dependencies:** Task 8

**Files likely touched:**
- `.codex/`
- `.claude/`
- `tests/test_codex_hooks.py`
- `tests/test_claude_hooks.py`
- README

**Estimated scope:** M

## Checkpoints

### Checkpoint A: Store and diagnostics

- [x] `loci stats --pretty` reads the intended MCP store by default.
- [x] `loci_stats` and `loci_analyze` work through MCP.
- [ ] Full test suite passes.

### Checkpoint B: Summarize decision

- [x] Evidence supports keeping or deleting `summarize`.
- [x] The chosen path has a task-level implementation plan.
- [x] No summarize work begins before the decision is explicit.

### Checkpoint C: CLI retirement

- [ ] MCP navigation is verified in a fresh session.
- [ ] CLI navigation duplication is removed or reduced to temporary wrappers.
- [ ] README and skills no longer encourage CLI navigation.

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| MCP tools are configured but not visible in the current session | CLI removal could strand the agent | Require fresh-session MCP smoke before removing CLI bridge commands |
| Stats reads the wrong store | Human sees empty/broken stats | Add explicit store resolution and show the active store in output |
| `analyze` produces noisy findings | Agents chase bad suggestions | Keep findings structured, thresholded, and framed as diagnostics, not orders |
| Summarize is stale but search still references summaries | Search behavior may become misleading | Audit scoring before either keeping or deleting summary support |
| Removing CLI breaks scripts/hooks | Hidden users fail | Search repo hooks/docs/tests first; remove only after MCP replacement and docs update |

## Open questions

- Should `loci stats --reset` remain, or should reset require an explicit store path to avoid wiping the wrong session log?
- Should `invalidate` exist as MCP, CLI, both, or neither? It is cache-destructive but useful for store-aware cleanup.
- If summarize is kept, should the generated summaries be considered cache metadata or part of an index format contract?
