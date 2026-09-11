---
name: loci
description: Agent-owned codebase navigation infrastructure. Use when repository work needs source retrieval or relationship tracing. A named target or small edit still needs inspection. Skip redundant retrieval only when relevant source has already been retrieved, remains current, and is sufficient for the action; task or file type alone is not an exemption.
---

# loci - Codex Workflow Guide

loci is agent-owned codebase navigation infrastructure. Run it yourself so
that codebase work uses bounded, exact retrieval instead of broad file reads.

## Evidence before action

First identify the source evidence the action needs, then choose the retrieval
route. A startup index summary, filename, function name, or recalled summary
is not source inspection. Named functions, README text and configuration values
still need their actual contents retrieved before acting on them.

Skip a redundant retrieval only when all three conditions hold:

- **Observed:** relevant source from the actual target checkout has been
  retrieved and is available in context, rather than only its name or a summary.
- **Current:** subsequent edits or checkout changes have not invalidated that
  evidence. Refresh affected source when freshness is uncertain.
- **Sufficient:** the retrieved material covers what this particular action
  depends on. A function's body alone does not establish its callers or the
  consequences of an interface change.

Use the bounded navigation routes below to obtain missing evidence. A justified
direct read under the fallback below can also supply evidence; choosing that
route still requires inspection. Reassess when the task or source changes.
Task size and file type do not establish these conditions. Pure conceptual work
without repository-source claims needs no repository retrieval.

## Core workflow

Prefer the local MCP server whenever its tools are available. Use the
repository root named by the task, not the shell cwd or an arbitrary parent:

```text
# Explicit rebuild or large change only:
loci_index(repo, incremental=true)
# Normal navigation, including unindexed roots and stale cached indexes:
loci_outline(repo) or loci_search(repo, query) -> optional search_id
loci_get(repo, symbol_ids, selected_from_search_id=search_id) only for deliberate search selections
# Source selected for a purpose, when loci_explore is available:
loci_explore(repo, intent, query, seed_ids=None)
loci_analyze(repo) when diagnostics are needed
```

Pass `repo` to every repository-scoped MCP tool. Do not introduce the legacy
`path` parameter in new guidance; it is advisory compatibility only for
`loci_index`, `loci_outline`, and `loci_verify`.

MCP retrieval tools create missing indexes and refresh stale indexes before
returning data, completing first-use indexing and retrieval in one call. This
freshness includes repository-local graph profiles and contributions, built-in
imports, references, and calls, Go module/workspace controls,
JavaScript/TypeScript package, workspace, and project controls, and Cargo
manifests. Use `loci_index` for an explicit rebuild or after large changes.

If MCP is unavailable, configure it before using the CLI as a steady-state
route. Read [setup-and-cli.md](references/setup-and-cli.md) for host setup,
store identity, and the bounded CLI fallback. If configuration or the current
runtime prevents MCP use, announce the temporary fallback and use the CLI
commands there. If loci is unavailable or the task is a standalone
documentation/config check where symbol navigation is irrelevant, say so and
use a targeted normal read.

## Navigate, then retrieve

1. Use normal MCP retrieval for first use; explicitly rebuild only when the
   task requires it. The CLI fallback still needs an initial `loci index`.
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

For compact source discovery, type dependencies, or known static dependents,
use `loci_explore` with `locate`, `type_dependencies`, or `impact`. Put the
specific field or contract of interest in `query`; pass exact `seed_ids` when
known. Inspect returned source, proof paths and omissions before deciding that
the context is sufficient. If the host lacks this tool, use search/get and the
diagnostic graph tools below. Exact edits still require the affected full source.

For intent selection, budgets, and graph-shaped questions, follow the rules in
[graph-navigation.md](references/graph-navigation.md). For exact response
schemas, pagination, coverage, and store-health semantics, read
[tool-contracts.md](references/tool-contracts.md). For language-specific
resolver guarantees and limits, read
[language-resolution.md](references/language-resolution.md).

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

- [setup-and-cli.md](references/setup-and-cli.md) — read when configuring MCP,
  verifying store ownership/namespace, or using the temporary CLI fallback.
- [tool-contracts.md](references/tool-contracts.md) — read when interpreting
  tool schemas, pagination, coverage, structured errors, graph-health output,
  or `loci_store_health` results.
- [graph-navigation.md](references/graph-navigation.md) — read when tracing
  dependencies, imports, references, calls, paths, or question-shaped graph
  evidence.
- [language-resolution.md](references/language-resolution.md) — read when a
  JavaScript/TypeScript, Go, or Rust import/reference resolution needs its
  supported controls, provenance, or failure limits.
