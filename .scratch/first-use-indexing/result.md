# First-use indexing fix

Date: 2026-09-09

## Read-only source-mirroring follow-up

`IndexStore.write` now copies each distinct source path once, preserving source
permissions and the existing mirror replacement behavior. Previously, the
second symbol from a `0400` file caused a duplicate `copy2` to overwrite the
read-only first copy and fail.

The new storage regression failed with that exact `PermissionError` before the
fix. Afterward, `tests/storage/test_index_store.py` passed all 62 tests, including
retrieval of multiple symbols and a second write replacing a read-only mirror.
The original source bytes and mode remain unchanged.

`tests/test_mcp_server.py::test_mcp_cold_and_warm_readonly_snapshot_sections`
passed through a fresh stdio MCP process: a normal search creates the index
for a snapshot-shaped root with a `0400` multi-section Markdown file, then
search/get retrieves both sections across cold and warm calls. No explicit
index call is made. `git diff --check` passed.

The existing Anvil `brain-w4-followup-run.mjs::recallPreflight` then passed
for p01, r01, and c01 with zero model runs. All delivered actual
`loci/indexed_section` evidence with positive byteCost: p01 2426/4802,
r01 3453/4804, c01 4258. Its snapshot immutability assertions passed.
Updated report: `/private/tmp/brain-loci-cold-check-V55Z8q-updated/result.json`.
The historical failed report remains at its original path.

## Mechanism and scope

`ensure_fresh_index` now treats a missing index as work for the existing
repository refresh lock. After acquiring it, the service reloads the index
and rechecks freshness before invoking `_index_repo_unlocked`. This reuses
store identity, namespace enforcement, catalog validation, and atomic writes.
Normal MCP source and graph retrieval already opt into this shared path.
Direct service/CLI reads without `ensure_fresh=True` retain their existing
explicit-index behavior. Read-only store-health diagnostics are unchanged.

Root validation rejects missing paths, files, and unreadable directories.
A generic initial indexing failure reports `INDEX_CREATION_FAILED`; existing
structured indexing errors propagate. Locks release on failure, and there is
no indexing retry loop. Waiting retains the existing bounded lock timeout.

## History

This was an uncovered path, not a demonstrated regression:

- `87a538a` / `f1886cf`: Claude/Codex session-start indexing.
- `18ab818`: shared hooks index the current Git root.
- `43efe12`: MCP introduced with an explicit pre-index requirement.
- `72bc285`: stale-index refresh added, but immediately required an existing
  index; its tests explicitly indexed before retrieving.
- `833ae99`: documented the continuing initial-index requirement.

A separately queried immutable wiki snapshot was never covered by indexing
the session's repository root.

## Acceptance

- `tests/test_service.py`: 126 passed, including concurrent first-use searches
  returning the fixture with exactly one build, warm reuse, initial failure
  propagation/lock cleanup, invalid/unreadable roots, and existing stale-refresh
  coverage.
- MCP schema and repository guidance checks: 14 passed.
- Skill validation passed.

Existing MCP processes cache the imported service module. Restart their MCP
server (or start a fresh host session) to load the changed code.

No captured W4 cases, live Brain, llm-wiki, or Anvil implementation was changed.

Installed-wrapper acceptance also passed: `/Users/brummerv/.local/bin/loci-mcp`
started against an absent disposable store with an explicit acceptance
namespace. Its first tool call was `loci_search` against
`brain-snapshots/acceptance/snapshots/<64-character digest>/wiki`, returning
`Cold Snapshot Fixture` from Markdown and persisting the index. Explicit
index calls: zero. Temporary files were cleaned up.

Final MCP acceptance: `tests/test_mcp_server.py` passed all 35 tests, including
cold Python and snapshot Markdown searches, independent cold outline/file/grep/
graph-health requests, persisted index assertions, stale refresh, and missing-root
error data. Combined relevant service/MCP/schema/guidance checks: 175 passed.
`git diff --check` passed. Both maintained Loci skills validated successfully.
