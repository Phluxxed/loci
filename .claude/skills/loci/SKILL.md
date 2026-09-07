---
name: loci
description: Agent-owned codebase navigation infrastructure. Use for non-trivial repository navigation, dependency tracing, review, or implementation that needs symbol or relationship retrieval. Skip standalone documentation, configuration, conceptual work, and edits confined to already-targeted files that need no further navigation.
---

# loci - Codex Workflow Guide

This compatibility entry is installed as a file symlink. Resolve the loaded
`SKILL.md` to its real source path before following relative links. The
[canonical skill](../../../skills/loci/SKILL.md) and its reference directory
own the maintained guidance; links below are relative to this source file.

loci is agent-owned codebase navigation infrastructure. Run it yourself so
that codebase work uses bounded, exact retrieval instead of broad file reads.

## Core workflow

Prefer the local MCP server whenever its tools are available. Use the
repository root named by the task, not the shell cwd or an arbitrary parent:

```text
# Unindexed repository, explicit rebuild, or large change only:
loci_index(repo, incremental=true)
# Normal navigation, including stale cached indexes:
loci_outline(repo) or loci_search(repo, query) -> optional search_id
loci_get(repo, symbol_ids, selected_from_search_id=search_id) only for deliberate search selections
loci_analyze(repo) when diagnostics are needed
```

Pass `repo` to every repository-scoped MCP tool. Do not introduce the legacy
`path` parameter in new guidance; it is advisory compatibility only for
`loci_index`, `loci_outline`, and `loci_verify`.

MCP read tools refresh stale indexes before returning cached data. This
freshness includes repository-local graph profiles and contributions, built-in
imports, references, and calls, Go module/workspace controls,
JavaScript/TypeScript package, workspace, and project controls, and Cargo
manifests. Run `loci_index` for a repository that has never been indexed; use
it again for an explicit rebuild or after large changes.

If MCP is unavailable, configure it before using the CLI as a steady-state
route. Read [setup-and-cli.md](../../../skills/loci/references/setup-and-cli.md) for host setup,
store identity, and the bounded CLI fallback. If configuration or the current
runtime prevents MCP use, announce the temporary fallback and use the CLI
commands there. If loci is unavailable or the task is a standalone
documentation/config check where symbol navigation is irrelevant, say so and
use a targeted normal read.

## Navigate, then retrieve

1. Index an unindexed target repository, or explicitly rebuild it when the
   task requires a fresh cache.
2. Use `loci_outline` when the file is known, or `loci_search` when only a
   symbol name or concept is known.
3. Use `loci_get` for the exact symbol IDs returned by outline/search. When a
   get is a deliberate selection from a non-empty search, pass that search's
   `search_id` as `selected_from_search_id`. Omit it for direct navigation,
   outline-driven navigation, bulk hydration, or any mixed-purpose batch; split
   mixed batches so only genuinely selected symbols carry lineage. Do not fetch
   an entire file when a symbol will answer the question.
4. Use `loci_file` only for targeted non-symbol ranges after locating the
   relevant file; use `loci_grep` for string literals, errors, or config keys.
5. Use `context` on focused retrieval when nearby lines are required, then
   inspect the returned source, line bounds, and signatures before reasoning.

For graph-shaped questions, follow the graph selection and evidence rules in
[graph-navigation.md](../../../skills/loci/references/graph-navigation.md). For exact response
schemas, pagination, coverage, and store-health semantics, read
[tool-contracts.md](../../../skills/loci/references/tool-contracts.md). For language-specific
resolver guarantees and limits, read
[language-resolution.md](../../../skills/loci/references/language-resolution.md).

## Safety and evidence boundaries

- Treat coverage on every search/grep result as part of the answer. `partial`
  and `unknown` coverage limit absence claims; an empty result never proves
  absence outside its stated query scope.
- Treat structured MCP failures under `structuredContent.error` as actionable
  errors with `code`, `message`, and `details`; do not silently reinterpret
  them as empty results.
- Treat unresolved, ambiguous, external, inaccessible, unsupported, or
  stale outcomes as bounded evidence that loci did not prove a relationship.
  Do not replace a failed resolution with repository-wide filename, package,
  or symbol-name guesses.
- Use `loci_analyze` when search misses, ranking is poor, or extraction quality
  looks suspect. Treat findings as diagnostics to inspect, not orders to
  follow blindly.
- Prefer `loci_stats` for structured retrieval/savings evidence. Use
  `loci stats --pretty` only for a human-readable shell or tmux view.
- Use `loci_list` when choosing among indexed roots, `loci_verify` for index
  integrity/content drift, `loci_store_health` for freshness/missing-root/
  overlap diagnostics, and `loci_graph_health` for graph-extension status.

## References

- [setup-and-cli.md](../../../skills/loci/references/setup-and-cli.md) — read when configuring MCP,
  verifying store ownership/namespace, or using the temporary CLI fallback.
- [tool-contracts.md](../../../skills/loci/references/tool-contracts.md) — read when interpreting
  tool schemas, pagination, coverage, structured errors, graph-health output,
  or `loci_store_health` results.
- [graph-navigation.md](../../../skills/loci/references/graph-navigation.md) — read when tracing
  dependencies, imports, references, calls, paths, or question-shaped graph
  evidence.
- [language-resolution.md](../../../skills/loci/references/language-resolution.md) — read when a
  JavaScript/TypeScript, Go, or Rust import/reference resolution needs its
  supported controls, provenance, or failure limits.
